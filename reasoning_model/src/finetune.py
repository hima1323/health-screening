"""LoRA fine-tune of Qwen2.5-3B-Instruct (MLX, 4-bit) on verified explanations -> results/lora/

Targets: the verified LLM output for each window; where the LLM failed verification, the template output
(verified by construction). Split by subject: the last --holdout subjects are never trained on and are used to
compare base vs LoRA hallucination rates (python src/finetune.py --compare).

    python src/finetune.py --build            # write results/lora_data/{train,valid}.jsonl
    python src/finetune.py --train            # mlx_lm lora (GPU, ~4 GB RAM; stop Ollama first)
    python src/finetune.py --compare          # base vs LoRA on held-out subjects via mlx_lm server
    python src/finetune.py --subject 0        # show the training example(s) built for one subject
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request

from load_adabase import subject_id
from reasoner import explain, is_fusion, prompt, rule_check, system, template, verify
from train import RES

MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"
DATA, ADAPTER = RES / "lora_data", RES / "lora"
HOLDOUT = 5  # subjects kept out of fine-tuning for the comparison


def load_pairs():
    """(evidence record, explanation record) per window and subject, single-model and fusion records together:
    one adapter learns both formats (they differ in the system prompt)."""
    out = {}
    for ev_dir, ex_dir in [("evidence", "explanations"), ("evidence_fusion", "explanations_fusion")]:
        for p in sorted((RES / ex_dir).glob("*.jsonl")) if (RES / ex_dir).exists() else []:
            ev = {(r["study"], r["level"], r["win_start"]): r for r in map(json.loads, open(RES / ev_dir / p.name))}
            out.setdefault(p.stem, []).extend(
                (ev[k], x) for x in map(json.loads, open(p))
                if x["generator"].startswith("llm:") and (k := (x["study"], x["level"], x["win_start"])) in ev)
    return out


def example(rec, expl):
    support, conflict = rule_check(rec)
    target = expl["output"]
    if not (target["evidence"] + target["conflicts"]) or verify(target, rec):  # failed / older looser verifier
        target = template(rec, support, conflict)
    return {"messages": [{"role": "system", "content": system(rec)},
                         {"role": "user", "content": prompt(rec, support, conflict)},
                         {"role": "assistant", "content": json.dumps(target)}]}


def split(pairs):
    sids = sorted(pairs)
    return sids[:-HOLDOUT], sids[-HOLDOUT:]


def build():
    pairs = load_pairs()
    train_s, hold = split(pairs)
    ex = [example(r, x) for s in train_s for r, x in pairs[s]]
    if len(ex) < 20:
        sys.exit(f"only {len(ex)} training examples from {len(train_s)} subjects; run the reasoner on more subjects")
    n_val = max(len(ex) // 10, 1)
    DATA.mkdir(parents=True, exist_ok=True)
    # validation = last ~10% of examples, i.e. the last training subject(s): validation loss is subject-wise
    with open(DATA / "train.jsonl", "w") as t, open(DATA / "valid.jsonl", "w") as v:
        for i, e in enumerate(ex):
            (v if i >= len(ex) - n_val else t).write(json.dumps(e) + "\n")
    print(f"train subjects {len(train_s)}, held-out {hold}, examples {len(ex) - n_val} train / {n_val} valid")


def train(iters):
    subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--model", MODEL, "--train", "--data", str(DATA),
                    "--adapter-path", str(ADAPTER), "--iters", str(iters), "--batch-size", "1", "--num-layers", "8",
                    "--learning-rate", "1e-4", "--mask-prompt", "--grad-checkpoint", "--steps-per-eval", "50",
                    "--max-seq-length", "2048"], check=True)


def serve(adapter):
    cmd = [sys.executable, "-m", "mlx_lm", "server", "--model", MODEL, "--port", "8080"]
    p = subprocess.Popen(cmd + (["--adapter-path", str(ADAPTER)] if adapter else []),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:8080/v1/models", timeout=2)
            return p
        except OSError:
            time.sleep(2)
    p.kill()
    sys.exit("mlx_lm server did not start")


def compare():
    pairs = load_pairs()
    _, hold = split(pairs)
    recs = [r for s in hold for r, _ in pairs[s]]
    rows = []
    for label, adapter in [("mlx:base", False), ("mlx:lora", True)]:
        srv = serve(adapter)
        try:
            res = [explain(r, label) for r in recs]
        finally:
            srv.kill()
        with open(RES / f"explanations_{label[4:]}_holdout.jsonl", "w") as fh:
            fh.writelines(json.dumps(x) + "\n" for x in res)
        for kind in ["single", "fusion"]:
            sub = [x for x, r in zip(res, recs) if is_fusion(r) == (kind == "fusion")]
            if not sub:
                continue
            n = len(sub)
            rows.append({"model": label, "record": kind, "subjects": len(hold), "windows": n,
                         "first_try_fail": sum(bool(x["errors_first"]) for x in sub) / n,
                         "final_unverified": sum(not x["verified"] for x in sub) / n,
                         "citation_accuracy": sum(x["cited_in_top6"] for x in sub) / max(sum(x["cited"] for x in sub), 1)})
            print(rows[-1], flush=True)
    import pandas as pd
    pd.DataFrame(rows).to_csv(RES / "lora_compare.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--subject")
    a = ap.parse_args()
    if a.subject:
        sid = subject_id(a.subject)
        r, x = load_pairs()[sid][0]
        print(json.dumps(example(r, x), indent=1))
    if a.build:
        build()
    if a.train:
        train(a.iters)
    if a.compare:
        compare()
