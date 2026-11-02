"""Local reasoning service for the Aura Screen demo: runs the expert system on one demo sample file and returns
everything the result screen shows. Standard library only; listens on 127.0.0.1 (the Aura server proxies to it).

    GET  /health                       -> {ok, samples, llm}
    GET  /samples                      -> [{id, title, dataset, note, reference_level}]
    POST /run   {sample_id, use_llm}   -> the result: level, rule, readings vs ranges, answers, explanation card
    POST /ask   {run_id, question}     -> follow-up answer from the session record + the knowledge text only

    python -m triage.demo_service [--port 5055]          (from reasoning_model/src; start_aura_demo.bat)

Demo only: draft rules, the DRAFT knowledge text (demo mode) and sample data; no user session is created.
"""
import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd

from triage.bench import dataset_bench as DB
from triage.bench.vignettes import to_record
from triage.demo_samples import load_samples
from triage.explainer import LABELS, NAMES, explain
from triage.followup_qa import answer, load_knowledge
from triage.reasoning_chain import apply
from triage.rules_engine import load_config

CFG = load_config()
KNOWLEDGE = load_knowledge(demo=True)
RUNS = {}
MAX_RUNS = 200
STATUS = {"in": "normal", "borderline": "near the limit", "out": "outside the range", "not_usable": "unclear",
          "not_measured": "not measured", "no_reference_range": "no range"}


def _range(r):
    if r is None:
        return None
    lo, hi = r
    return f"{lo:g}–{hi:g}" if lo is not None and hi is not None else f"≥ {lo:g}" if lo is not None else f"≤ {hi:g}"


def run_sample(sample, use_llm=True):
    t0 = time.perf_counter()
    vig = DB.to_vignettes(pd.DataFrame([sample["case"]]), CFG)[0][0]
    rec = apply(to_record(vig, CFG), CFG)
    first = rec["decision"]
    if first["level"] == "REMEASURE":                         # one rest-and-remeasure round, as in the kiosk
        rec = apply(to_record(vig, CFG, after_rest=True), CFG)
    card, log = explain(rec, CFG, use_llm=use_llm)
    ch = {s["step"]: s for s in rec["chain"]}
    readings = [{"key": i["name"], "measure": NAMES.get(i["name"], i["name"]), "unit": i["unit"],
                 "readings": i["readings"], "value": i["value"], "normal": _range(i.get("normal")),
                 "urgent": _range(i.get("urgent")), "margin": i["margin"], "quality": i["quality"],
                 "status": i["status"], "status_text": STATUS.get(i["status"], i["status"])}
                for i in ch["interpretation"]["items"]]
    d = rec["decision"]
    ref = sample.get("reference_level")
    run_id = uuid.uuid4().hex[:10]
    out = {"run_id": run_id,
           "sample": {k: sample.get(k) for k in ("id", "title", "dataset", "source", "note", "reference_level",
                                                 "camera_reference")},
           "level": d["level"], "label": LABELS[d["level"]],
           "rule": {"id": d["rule_id"], "reason": d["reason"],
                    "also_matched": [m["rule_id"] for m in d["also_matched"]]},
           "remeasured": first["level"] == "REMEASURE",
           "first_rule": first["rule_id"] if first["level"] == "REMEASURE" else None,
           "readings": readings,
           "answers": [{"id": a["id"], "item": a["item"].replace("_", " "), "answer": a["answer"]}
                       for a in rec["answers"] if a["answer"] not in ("no",)],
           "scores": [{"name": s["name"], "value": s["value"]} for s in rec["scores"]],
           "uncertainty": [u["text"] + (": " + ", ".join(NAMES.get(n, n) for n in u["names"]) if u.get("names") else "")
                           for u in ch["uncertainty"]["items"]],
           "card": card, "text_source": log["source"],
           "reference_match": None if not ref else ref == d["level"],
           "rules_status": CFG["rules"]["status"], "rules_version": CFG["rules"]["version"],
           "seconds": round(time.perf_counter() - t0, 2)}
    RUNS[run_id] = rec
    while len(RUNS) > MAX_RUNS:
        RUNS.pop(next(iter(RUNS)))
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "samples": len(load_samples()), "rules": CFG["rules"]["version"]})
        if self.path == "/samples":
            return self._send(200, [{k: s.get(k) for k in ("id", "title", "dataset", "note", "reference_level")}
                                    for s in load_samples().values()])
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            self._post()
        except Exception as e:                              # always answer: a dropped connection looks like a dead service
            import traceback
            traceback.print_exc()
            self._send(500, {"error": f"The reasoning model failed on this sample: {e}"})

    def _post(self):
        b = self._body()
        if self.path == "/run":
            sample = load_samples().get(str(b.get("sample_id")))
            if not sample:
                return self._send(404, {"error": f"unknown demo sample {b.get('sample_id')}"})
            return self._send(200, run_sample(sample, use_llm=bool(b.get("use_llm", True))))
        if self.path == "/ask":
            rec = RUNS.get(str(b.get("run_id")))
            q = str(b.get("question") or "").strip()[:500]
            if rec is None:
                return self._send(404, {"error": "This result has expired. Scan the code again."})
            if not q:
                return self._send(400, {"error": "Type a question."})
            res = answer(q, rec, CFG, KNOWLEDGE)
            return self._send(200, {"answer": res["answer"], "sources": res["sources"], "by": res["by"]})
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):                     # quiet console; one line per request
        print(f"[reasoning] {self.command} {self.path} {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5055)
    a = ap.parse_args()
    if not load_samples():
        raise SystemExit("no demo samples: run python -m triage.demo_samples --build first")
    print(f"Aura reasoning service on http://127.0.0.1:{a.port} ({len(load_samples())} demo samples)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
