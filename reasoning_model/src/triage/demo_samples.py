"""Demo sample files for presentations: one small JSON file per case, built from the datasets already on this
machine, so a demo never needs live input or anything fetched from a website.

Sources (test data only: nothing used for rule derivation or training):
  MIMIC-IV-ED Demo   test subjects (ed_cases.mimic_dev_mask): triage vitals, chief complaint -> red flags, ESI
  Yale ED            the benchmark's test split (seed 0), ages 18-65: vitals, complaint -> red flags, ESI, age
  rPPG (rppg1)       the camera heart rate our CVPR Lab P4 model measured on held-out videos of MCD-rPPG (rest and
                     after exercise), UBFC-rPPG and MPSC-rPPG, with the contact-sensor reference beside it
  Vignettes          the draft vignettes (made up by the developer, unlabelled)
A field the dataset does not have stays empty (not invented): e.g. the rPPG samples have only a heart rate and no
answers, and the card then says what was not measured or asked.

Each file is {id, title, dataset, source, note, case (dataset_bench row format), reference_level, camera_reference}.

    python -m triage.demo_samples --build          (from reasoning_model/src) -> reasoning_model/demo_samples/
"""
import argparse
import json

import numpy as np

from triage.evidence import ROOT
from triage.rules_engine import load_config

OUT = ROOT / "demo_samples"
RPPG_RESULTS = ROOT.parent / "rppg1" / "runs" / "results"


def _f(x, nd=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def ed_case_row(c, cfg, with_age):
    flags = set(c["red_flags"])
    row = {"case_id": str(c["case_id"]), "hr": _f(c["hr"], 0), "rr": _f(c["rr"], 0), "temp_c": _f(c["temp_c"]),
           "spo2": _f(c["spo2"], 0), "sbp": _f(c["sbp"], 0), "dbp": _f(c["dbp"], 0),
           "complaint": c["complaint"] or "", "esi": _f(c["esi"], 0),
           "admitted": "yes" if c["admitted"] else "no"}
    for it in cfg["red_flags"]["urgent_items"] + ["self_harm"]:
        row[it] = "yes" if it in flags else "no"
    if with_age and c.get("age") == c.get("age") and c.get("age") is not None:
        row["age"] = int(c["age"])
    return {k: v for k, v in row.items() if v is not None}


def ref_level(esi, admitted):
    return "URGENT" if esi <= 2 else "SEE_DOCTOR_SOON" if esi == 3 or admitted else "SELF_CARE"


def pick_ed(df, rng, n_per):
    """A spread over the reference levels, with and without a red-flag complaint."""
    df = df[df["hr"].notna() & df["rr"].notna() & df["temp_c"].notna()].copy()
    df["ref"] = [ref_level(e, a) for e, a in zip(df["esi"], df["admitted"])]
    df["has_flag"] = df["red_flags"].map(bool)
    out = []
    for ref, flag in (("URGENT", True), ("URGENT", False), ("SEE_DOCTOR_SOON", False), ("SELF_CARE", False)):
        sub = df[(df["ref"] == ref) & (df["has_flag"] == flag)]
        if len(sub):
            out += sub.sample(min(n_per, len(sub)), random_state=int(rng.integers(1e6))).to_dict("records")
    return out


def describe(c):
    bits = [f"HR {c['hr']:.0f}" if c.get("hr") == c.get("hr") else None,
            f"RR {c['rr']:.0f}" if c.get("rr") == c.get("rr") else None,
            f"{c['temp_c']:.1f} °C" if c.get("temp_c") == c.get("temp_c") else None]
    return ", ".join(b for b in bits if b)


def build():
    from triage.bench import ed_cases, mimic_ed, yale
    from triage.bench.vignettes import load_vignettes
    cfg = load_config()
    rng = np.random.default_rng(7)
    samples = []

    # a machine without the ED datasets (the hosted demo) builds the rPPG and vignette samples only
    try:
        mi = mimic_ed.load(cfg=cfg)
    except (FileNotFoundError, ImportError) as e:
        print(f"skipping MIMIC-IV-ED samples: {e}")
        mi = None
    if mi is not None:
        mi = mi[mi["esi"].notna()]
        mi = mi[~ed_cases.mimic_dev_mask(mi)]
    for c in pick_ed(mi, rng, 1) if mi is not None else []:
        samples.append({"id": f"mimic-{c['case_id']}", "dataset": "MIMIC-IV-ED Demo",
                        "title": f"ED visit: {(c['complaint'] or 'no complaint recorded').lower()}",
                        "source": "MIMIC-IV-ED Demo v2.2 (PhysioNet, open), test subjects only",
                        "note": f"Triage vitals {describe(c)}; ESI {int(c['esi'])}"
                                f"{', admitted' if c['admitted'] else ''}. No age in the ED Demo.",
                        "case": ed_case_row(c, cfg, with_age=False),
                        "reference_level": ref_level(c["esi"], c["admitted"])})

    try:
        ya = yale.load()
    except (FileNotFoundError, ImportError) as e:
        print(f"skipping Yale ED samples: {e}")
        ya = None
    if ya is not None:
        ya = ya[ya["esi"].notna()]
        ya = ya[np.random.default_rng(0).random(len(ya)) >= 0.2]             # benchmark test split
        ya = ya[(ya["age"] >= 18) & (ya["age"] <= 65)]
    for c in pick_ed(ya, rng, 1) if ya is not None else []:
        samples.append({"id": f"yale-{c['case_id']}", "dataset": "Yale ED (Hong et al. 2018)",
                        "title": f"ED visit, age {int(c['age'])}: {(c['complaint'] or 'no complaint').split(';')[0]}",
                        "source": "Yale ED triage data (Zenodo 1308993, open), benchmark test split",
                        "note": f"Triage vitals {describe(c)}; ESI {int(c['esi'])}"
                                f"{', admitted' if c['admitted'] else ''}.",
                        "case": ed_case_row(c, cfg, with_age=True),
                        "reference_level": ref_level(c["esi"], c["admitted"])})

    rp = [("CVPR_P4_e30_MCD.json", "MCD-rPPG", ["IriunWebcam_before", "IriunWebcam_after"], 2),
          ("CVPR_P4_e30_MCD_UBFC.json", "UBFC-rPPG", [""], 2), ("CVPR_P4_e30_MCD_MPSC.json", "MPSC-rPPG", [""], 1)]
    for fname, ds, kinds, n in rp:
        p = RPPG_RESULTS / fname
        if not p.exists():
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))["per_video"]
        for kind in kinds:
            cand = [r for r in rows if kind in r["video"]]
            cand.sort(key=lambda r: abs(r["hr_pred"] - r["hr_label"]))
            for r in cand[:n]:
                after = "after" in r["video"]
                samples.append({
                    "id": f"rppg-{ds.split('-')[0].lower()}-{r['video']}", "dataset": f"{ds} (camera heart rate)",
                    "title": f"Face video, {ds}" + (" after exercise" if after else " at rest" if "before" in
                                                    r["video"] else ""),
                    "source": f"Heart rate measured from the face video by our rPPG model (CVPR Lab P4, trained on "
                              f"MCD-rPPG); {ds} video {r['video']} (held out)",
                    "note": f"Camera {r['hr_pred']:.0f} bpm vs contact sensor {r['hr_label']:.0f} bpm. Only the heart "
                            "rate comes from this dataset: breathing, temperature and the questions are empty.",
                    "case": {"case_id": r["video"], "hr": round(r["hr_pred"]), "quality_heart_rate": 0.9,
                             **({"exercise_last_30min": "yes"} if after else {})},
                    "reference_level": None,
                    "camera_reference": {"camera_bpm": round(r["hr_pred"], 1), "sensor_bpm": round(r["hr_label"], 1)}})

    for v in load_vignettes():
        if v["id"] not in ("V007", "V012", "V005", "V015"):
            continue
        case = {"case_id": v["id"], **({"age": v["age"]} if v.get("age") else {}), **v["answers"]}
        for name, col in (("heart_rate", "hr"), ("resp_rate", "rr"), ("temperature", "temp_c")):
            x = v["measurements"].get(name)
            if x is not None:
                xs = x if isinstance(x, list) else [x, x]
                case[col], case[f"{col}_2"] = xs[0], xs[-1]
            y = (v.get("measurements_after_rest") or {}).get(name)
            if y is not None:
                case[f"{col}_rest"] = y[0] if isinstance(y, list) else y
        case.update({k.lower(): s for k, s in (v.get("scores") or {}).items()})
        samples.append({"id": f"vignette-{v['id']}", "dataset": "Draft vignette (made up)",
                        "title": v.get("narrative", v["id"]), "source": "reasoning_model/vignettes (developer draft)",
                        "note": "A made-up case written to show one rule path; not from a real person.",
                        "case": case, "reference_level": None})

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for s in samples:
        (OUT / f"{s['id']}.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return samples


def load_samples():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT.glob("*.json"))}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    s = build() if a.build else list(load_samples().values())
    for x in s:
        print(f"{x['id']:<45} {x['dataset']:<34} ref {x.get('reference_level') or '-':<16} {x['title'][:60]}")
    print(f"{len(s)} sample files in {OUT.relative_to(ROOT)}")
