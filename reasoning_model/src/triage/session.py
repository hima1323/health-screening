"""One kiosk session, start to end (starter kit phase E3):

    consent -> scope (age, pregnancy) -> rest measurement (quality checked) -> questions -> rule engine
    -> REMEASURE once (rest, measure again, decide again) -> reasoning chain -> explanation -> follow-up Q&A -> end

The UI and the sensors are injected as functions, so the same flow runs in the kiosk app, in tests and in scripted
demos:
    measure(round)  -> {"measurements": [{name, value, unit, quality, source, error_margin?, repeat_values?}],
                        "flags": [...]}                             round = 1, or 2 after a REMEASURE
    ask(question)   -> answer, or (answer, confirmed)               question = an entry of questionnaire.questions()
    wait(seconds)   -> None                                         the REMEASURE rest (no-op in tests)
Out of scope (R00): no measurement; the red-flag and self-harm questions are still asked, because they override the
scope rule. Without consent nothing is measured, asked or stored. A user session needs a clinician-approved config
(safety rule 2); `demo=True` allows the drafts for synthetic data only.
"""
import json
import time
import uuid

from triage.evidence import ROOT, add_measurement, new_record
from triage.explainer import explain
from triage.questionnaire import pending, record_answers
from triage.reasoning_chain import apply
from triage.rules_engine import require_approved

LOGS = ROOT / "results" / "triage" / "sessions"          # git-ignored; anonymous session IDs only
REST_S = 300


class Session:
    def __init__(self, cfg, measure, ask, wait=lambda s: None, demo=False, use_llm=True, log=True):
        if not demo:
            require_approved(cfg)
        self.cfg, self.measure, self.ask, self.wait = cfg, measure, ask, wait
        self.demo, self.use_llm, self.log = demo, use_llm, log
        self.id = ("demo-" if demo else "") + uuid.uuid4().hex[:12]
        self.events, self.answers, self.unconfirmed = [], {}, set()
        self.rec = self.card = self.explain_log = None

    def _event(self, step, **kw):
        self.events.append({"step": step, "t": round(time.perf_counter() - self._t0, 3), **kw})

    def _ask(self, sections, only=None):
        skipped = set()
        while True:                    # recomputed after every answer, so ask_if follow-ups are asked in turn
            q = next((q for q in pending(self.cfg, self.answers, sections)
                      if q["item"] not in skipped and (not only or q["item"] in only)), None)
            if q is None:
                return
            got = self.ask(q)
            value, confirmed = got if isinstance(got, tuple) else (got, True)
            if value is None:                                   # skipped: not answered
                skipped.add(q["item"])
                continue
            self.answers[q["item"]] = value
            if not confirmed:
                self.unconfirmed.add(q["item"])

    def _measure(self, rnd):
        got = self.measure(rnd)
        self.rec["measurements"] = []
        for m in got.get("measurements", []):
            add_measurement(self.rec, m["name"], m["value"], m["unit"], m["quality"], m["source"],
                            m.get("error_margin"), m.get("repeat_values"))
        self.rec["flags"] = [f for f in self.rec["flags"] if f == "remeasured"] + list(got.get("flags", []))
        self._event("measure", round=rnd, n=len(self.rec["measurements"]), flags=list(got.get("flags", [])))

    def _decide(self):
        self.rec["answers"], self.rec["scores"] = [], []
        record_answers(self.rec, self.cfg, self.answers, self.unconfirmed)
        apply(self.rec, self.cfg)
        self._event("decide", level=self.rec["decision"]["level"], rule=self.rec["decision"]["rule_id"])

    def run(self):
        self._t0 = time.perf_counter()
        self._ask(["consent"])
        if self.answers.get("consent") != "yes" or "consent" in self.unconfirmed:
            self._event("end", status="no_consent")
            return {"status": "no_consent", "session_id": self.id}
        self.rec = new_record(self.id, self.cfg)
        self._ask(["scope"])
        self._decide()
        if self.rec["decision"]["rule_id"] == "R00_out_of_scope":
            # no measurement, but red flags and self-harm still override the scope rule
            self._ask(["red_flags"])
            self._ask(["mood"], only={"self_harm"})
            self._decide()
        else:
            self._measure(1)
            self._ask(["red_flags", "context", "duration", "mood"])
            self._decide()
            if self.rec["decision"]["level"] == "REMEASURE":
                self.wait(REST_S)
                self.rec["flags"].append("remeasured")
                self._measure(2)
                self._decide()
        self.card, self.explain_log = explain(self.rec, self.cfg, use_llm=self.use_llm)
        self._event("explain", source=self.explain_log["source"], seconds=self.explain_log["seconds"])
        self._event("end", status="done")
        if self.log:
            self.save()
        return {"status": "done", "session_id": self.id, "level": self.rec["decision"]["level"],
                "rule_id": self.rec["decision"]["rule_id"], "card": self.card, "record": self.rec,
                "events": self.events}

    def save(self):
        LOGS.mkdir(parents=True, exist_ok=True)
        path = LOGS / f"{self.id}.json"
        path.write_text(json.dumps({"record": self.rec, "card": self.card, "explain": self.explain_log,
                                    "events": self.events}, indent=1), encoding="utf-8")
        return path


# ---------------------------------------------------------------- scripted sessions (tests, demos)

UNITS = {"heart_rate": ("bpm", "rppg"), "resp_rate": ("/min", "thermal_nostril"),
         "temperature": ("C", "thermal_canthus"), "spo2": ("%", "device"), "sbp": ("mmHg", "device"),
         "dbp": ("mmHg", "device")}


def scripted(script):
    """script = {"answers": {item: value or [value, confirmed]}, "vitals": {name: [r1, r2] or None},
    "vitals_after_rest": {...} (round 2), "quality": {name: q}, "flags": [...]} -> (measure, ask)."""
    def measure(rnd):
        vitals = script.get("vitals_after_rest", script["vitals"]) if rnd == 2 else script.get("vitals", {})
        ms = []
        for name, reps in vitals.items():
            unit, source = UNITS[name]
            q = script.get("quality", {}).get(name, 0.9)
            if reps is None:
                ms.append({"name": name, "value": None, "unit": unit, "quality": 0.0, "source": source})
            else:
                ms.append({"name": name, "value": round(sum(reps) / len(reps), 2), "unit": unit, "quality": q,
                           "source": source, "repeat_values": list(reps)})
        return {"measurements": ms, "flags": script.get("flags", []) if rnd == 1 else []}

    def ask(q):
        a = script.get("answers", {}).get(q["item"], DEFAULT_ANSWERS.get(q["item"]))
        if a is None and q["options"] and "no" in q["options"]:
            a = "no"
        return tuple(a) if isinstance(a, list) else a
    return measure, ask


DEFAULT_ANSWERS = {"consent": "yes", "age": 35, "pregnant": "no", "has_symptom": "no",
                   "phq2_1": "Not at all", "phq2_2": "Not at all", "gad2_1": "Not at all", "gad2_2": "Not at all"}
