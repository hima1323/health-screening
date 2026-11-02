# Hybrid expert triage system: implementation status

Implements `CLAUDE_CODE_EXPERT_TRIAGE_SYSTEM.md` (the triage starter kit). Everything is **DRAFT**: no rule,
range, red flag, message, knowledge text or contact number is clinician-approved yet. User sessions are blocked until
it is; `--demo` / `demo=True` runs the drafts on synthetic or sample data only.

Commands run from `reasoning_model/src` with `..\.venv\Scripts\python.exe -m ...`.

| Phase | What | Files | Status |
|---|---|---|---|
| E0 | Kit import, schemas, rule engine, tests | `configs/triage/*.yaml`, `evidence/`, `templates/`, `knowledge/triage_knowledge_DRAFT.md`, `src/triage/schema.py`, `rules_engine.py`, `tests/triage/` | done; 242 tests, 13/13 rules covered |
| E1.1 | Source check table | `triage.derive.source_check` -> `evidence/source_check.csv` | table built (41 rows); **people fill in the official values** |
| E1.2 | MIMIC-IV-ED dev bands, cut-off sens/FPR with kiosk error, red-flag coverage | `triage.derive.mimic_dev_bands` | runs on the open Demo (27 dev visits: tests the code only); **full release needs the signed DUA** |
| E1.3 | NHANES over-referral | `triage.derive.nhanes_overreferral` | code ready; **needs the two CDC files** (`--download`, ~3 MB) |
| E1.4 | Rule-learning suggestions | `triage.derive.rule_learning [--yale]` | runs (Yale dev, ages 18-65); `imodels` rule lists optional, not installed |
| E1.5 | Delphi pack + scoring | `triage.derive.delphi --round 1` / `--score` | pack built: `results/triage/delphi_round1.xlsx`; **needs 3-5 clinicians** |
| E1.6 | Lock v1.0 | `rules_engine --approval` lists what blocks it | **clinician sign-off** |
| E2 | Measurement agents | `src/triage/measure/` | existing (Phase M) |
| E3 | Questionnaire + session flow | `questionnaire.py`, `session.py` | done; 21 scripted sessions pass |
| E4 | Explainer, verifier, follow-up Q&A | `llm.py`, `explainer.py`, `verify.py`, `followup_qa.py`; `triage.bench.reasoning_bench` | done; benchmark: `results/triage/reasoning_bench.md` |
| E5 | Measurement benchmark | `bench/measurement_bench.py` (stub) | the rPPG benchmark lives in `rppg1/bench`; error margins are still placeholders |
| E6 | Vignette benchmark | `triage.bench.vignettes [--variants] [--llm]`, `vignettes/draft_vignettes.yaml` | runner done; 22 **unlabelled draft** vignettes; **clinicians write / label ~120** |
| E7 | ED benchmark | `triage.bench.run_bench` (existing) | MIMIC test now excludes the E1 dev subjects; re-run after config changes |
| E8 | Wellness panel | `record["wellness"]`, never read by the rules (tested) | existing |
| E9 | Kiosk app | `kiosk_app.py`, `start_kiosk_demo.bat` | demo gate, consent + scope questions, explanation, follow-up chat |
| E10 | Sign-off, user test, pilot | `templates/clinician_review_checklist.md` | **needs ethics approval** |

## Changes to the existing configs (for the clinician)

- Item ids and wording follow the kit: `stroke_signs`, `worst_headache`, `feeling_unwell`; new red flags
  `severe_bleeding`, `severe_allergy`; new context item `fever_feeling`; consent and scope (age, pregnancy) questions.
- New rules: `R00_out_of_scope` (NOT_SUITABLE; **placed after the red-flag and self-harm rules**, not first as in the
  kit, so a red flag still gives URGENT for anyone; the card also shows the emergency number) and `R06a_fever_unwell`.
- Values from the kit: minimum quality 0.6 (was 0.5); athlete lower heart-rate bound 50 (was 45); fever cut-off 38.0;
  population 18-65. Kept from the project where the kit is ambiguous: SpO2 normal >= 95 (kit: "94-95 = 1 point,
  clinician to set"), placeholder error margins (HR 5, RR 3, temperature 0.5).
- The kit's `when:` strings are written as structured conditions (the kit allows this); no string is evaluated.

## Findings so far (draft rules, development data)

- Yale dev (ages 18-65): the draft rules call 37% of ESI 1-2 visits URGENT (specificity 0.90); a depth-3 tree suggests
  an urgent heart-rate split near 108 bpm (draft: 131). Suggestion for the Delphi panel only.
- MIMIC Demo dev: about a third of urgent visits had no red flag and normal kiosk vitals (27 visits; code check only).
- The LLM never decides: the level, advice, contacts and disclaimer come from code; every LLM text passes the
  verifier or is replaced by the deterministic template.

## Aura Screen presentation demo (QR -> sample data -> reasoning model)

`start_aura_demo.bat` (repo root) starts three windows: the reasoning service (`python -m triage.demo_service`,
127.0.0.1:5055), the Aura server without MongoDB (`DEMO_WITHOUT_DB=1`) and the Aura app over self-signed HTTPS
(`HTTPS=1 npx vite`, so a phone may use its camera).

1. Laptop / kiosk screen: `https://localhost:5173/kiosk?demo=1`. Pick a demo sample (or Random); the screen shows a
   signed QR code that carries it and changes every 10 minutes.
2. Phone on the same Wi-Fi: `https://<laptop IP>:5173/demo` (accept the certificate warning once; allow the camera;
   Windows may ask to let Node through the firewall the first time). Tap "Scan the kiosk code".
3. The phone shows the analysing steps, then the result: the level, the demo data it came from (and whether the rules
   agree with the ED reference level), each reading against its range, the rule and the plain-language reasons, the
   advice and contacts, and a box for follow-up questions. "No camera? Choose a sample" works without scanning.
   A signed-in patient scanning the same code from the Scan Hub lands on the same result.

Sample files: `python -m triage.demo_samples --build` -> `reasoning_model/demo_samples/` (19 files, git-ignored):
4 MIMIC-IV-ED Demo test stays, 4 Yale ED test visits (ages 18-65), 7 camera heart rates measured by our rPPG model on
held-out MCD / UBFC / MPSC videos, 4 draft vignettes. A field a dataset lacks stays empty; nothing is invented.
