# Brief for Claude Code: integrate the guided-triage ("see a doctor or not") pipeline into the project

**Read first:**
- `START_HERE_CLAUDE_CODE.md` (rules, environment);
- `CLAUDE_CODE_APPROACH_A.md` (evidence record, verifier, explainer you will reuse);
- `CLAUDE_CODE_DATASETS_TRAIN_TEST_BENCHMARK.md` (rPPG/thermal extractors, benchmark conventions);
- `TRIAGE_AGENT_EVIDENCE_AND_DATASETS.md` (papers and datasets for this brief).

This brief adds a new, separate **triage track**. It does not change the cognitive-load model. The load model can appear in
the kiosk only as optional wellness information (§9) and **never changes the triage decision**.

---

## 0. What is being built (one paragraph)

The kiosk measures vital signs without contact (rPPG heart rate, thermal temperature and breathing rate; optionally a BP
cuff and a clip oximeter). It asks a short fixed questionnaire (red-flag symptoms, context, PHQ-2 / GAD-2) and writes
everything into an **evidence record**. A **rule engine** with clinician-reviewed rules decides one of four levels:
**URGENT / SEE A DOCTOR SOON / SELF-CARE & MONITOR / RETAKE**. Code builds a **reasoning chain**, and a **local LLM**
explains it and answers follow-up questions, checked by a **verifier**. The LLM never picks or changes the level. Everything
is benchmarked in four layers: measurement, decision, reasoning, system.

## 1. Non-negotiable safety and compliance rules

1. **The decision is made only by the rule engine.** No ML model or LLM output can set or change the level.
2. **All thresholds, red flags and wording are DRAFT until a clinician signs them off.** Each rule carries
   `status: draft|approved`, `reviewed_by`, `review_date`. The kiosk refuses to run user tests while any rule is `draft`.
3. **When in doubt, refer.** Red-flag symptoms override every sensor value. A borderline value is re-measured, never ignored.
4. **Never output "you don't need a doctor".** The SELF-CARE wording is fixed: "No warning signs were found by this check.
   If you feel unwell, see a doctor anyway."
5. **No diagnoses, no medication or dosing advice, no disorder names** in any generated text (verifier-enforced).
6. **Self-harm item positive → URGENT + crisis resources.** Phone numbers come from config (`configs/triage_contacts.yaml`;
   for India e.g. 112 emergency and Tele-MANAS 14416; the team verifies the numbers before use).
7. **MIMIC data use agreement:**
   - MIMIC-IV-ED / MIETIC / MIMIC-IV-Ext-CDS stay on the approved machine under `data/restricted/` (git-ignored);
   - they are **never sent to any external API or online LLM**: only local Ollama;
   - no row-level outputs leave the machine; results files contain aggregates only;
   - keep the data use agreement and the credential holder's name in `data/restricted/README_ACCESS.md`.
8. This is a **research / wellness prototype** run under ethics approval, not a medical device. Every result screen carries
   "This check is informational and is not a medical diagnosis."
9. Usual project rules: 8 GB RAM; `n_jobs ≤ 6`; never commit `data/` or `results/`; no secrets in files; show a diff before
   editing existing `src/*.py`.

---

## 2. File layout (new)

```
configs/triage/
  vital_ranges.yaml        # reference ranges + device error margins (DRAFT until reviewed)
  red_flags.yaml           # symptom list, user-facing wording, synonyms, chief-complaint regex (DRAFT)
  questionnaire.yaml       # fixed items, answer options, scoring (PHQ-2, GAD-2), skip logic
  rules.yaml               # ordered rule table (DRAFT) -> level + reason codes
  contacts.yaml            # emergency / crisis numbers (verified by team)
knowledge/triage_knowledge.md   # clinician-reviewed plain-language text the explainer may use
src/triage/
  measure/hr_rppg.py  measure/thermal_vitals.py  measure/devices.py   # vitals + quality
  questionnaire.py  evidence.py  rules_engine.py  reasoning_chain.py
  explainer.py  verify.py  followup_qa.py  session.py              # session = orchestration
  kiosk_app.py                                                      # local UI (Streamlit)
src/triage/bench/
  vignettes.py  mimic_ed.py  yale.py  ktas.py  mietic.py  cds.py
  baselines.py  metrics.py  run_bench.py  measurement_bench.py
tests/triage/                       # unit tests for every rule path + verifier + mappings
results/triage/                     # aggregate results only
data/restricted/{mimic_iv_ed,mietic,mimic_iv_ext_cds}/    # git-ignored, approved machine only
data/public/{yale_triage,ktas,mimic_iv_ed_demo,bidmc,vitaldb}/
```

---

## 3. Core data structures

### 3.1 Evidence record (`src/triage/evidence.py`, JSON Schema in `configs/triage/evidence.schema.json`)
```json
{"session_id":"…","version":{"rules":"v0.3","ranges":"v0.2","code":"<git sha>"},
 "measurements":[
   {"id":"M1","name":"heart_rate","value":108,"unit":"bpm","error_margin":3,"quality":0.92,
    "n_readings":2,"source":"rppg","repeat_values":[109,107]},
   {"id":"M2","name":"temperature","value":36.9,"unit":"C","error_margin":0.4,"quality":0.88,"source":"thermal_canthus"},
   {"id":"M3","name":"resp_rate","value":16,"unit":"/min","error_margin":2,"quality":0.80,"source":"thermal_nostril"}],
 "answers":[
   {"id":"Q1","item":"chest_pain","answer":"no","confirmed":true},
   {"id":"Q7","item":"exercise_last_30min","answer":"no","confirmed":true},
   {"id":"Q9","item":"caffeine_last_2h","answer":"yes","confirmed":true}],
 "scores":[{"id":"S1","name":"PHQ2","value":1},{"id":"S2","name":"GAD2","value":2}],
 "flags":[], "decision":null, "chain":null}
```

### 3.2 Rule table (`configs/triage/rules.yaml`). Ordered; the first match wins. Values are **DRAFT placeholders**
```yaml
version: v0.1
status: draft            # draft | approved
reviewed_by: null
rules:
  - id: R01_red_flag
    level: URGENT
    when: any_answer_in(red_flags.urgent_items, "yes")
    reason: "A symptom that needs prompt medical attention was reported."
  - id: R02_self_harm
    level: URGENT
    when: answer(self_harm) == "yes"
    action: show_crisis_contacts
  - id: R03_quality
    level: RETAKE
    when: any_measurement(quality < ranges.min_quality) or face_not_found
  - id: R04_recent_exercise_borderline
    level: REMEASURE          # internal: wait 5 min, then re-measure once
    when: answer(exercise_last_30min) == "yes" and any_outside_range(margin=error_margin)
  - id: R05_vital_far_out
    level: URGENT
    when: any_outside_range(range=ranges.urgent, confirmed_repeat=true)
  - id: R06_vital_out
    level: SEE_DOCTOR_SOON
    when: any_outside_range(range=ranges.normal, margin=error_margin, confirmed_repeat=true)
  - id: R07_mood_screen
    level: SEE_DOCTOR_SOON
    when: score(PHQ2) >= 3 or score(GAD2) >= 3
    wording_key: talk_to_professional
  - id: R08_persistent_symptom
    level: SEE_DOCTOR_SOON
    when: answer(symptom_duration_days) >= questionnaire.persistent_days
  - id: R99_default
    level: SELF_CARE
```
- `vital_ranges.yaml` holds `normal` and `urgent` ranges per measure, plus `error_margin` per device. The error margins come
  from the **measured** Layer-1 results (§6), never from guesses.
- Starting points for the clinician to review (adult reference values, to be confirmed):
  - resting HR normal 60–100 bpm (lower bound adjusted for athletes via a question);
  - RR 12–20 /min;
  - temperature: a calibrated fever cut-off;
  - urgent cut-offs set by the clinician, e.g. informed by the NEWS/NEWS2 bands.
- Rule conditions are a **small fixed set of functions** implemented in `rules_engine.py`. There is no `eval` of free text.
  Every function has unit tests.

### 3.3 Reasoning chain (`reasoning_chain.py`), computed by code
```
evidence → interpretation (value vs range ± margin, repeats, quality) → context (answers that change interpretation)
→ rule fired (id + plain reason) → uncertainty (what could explain it; what was not measured) → advice (fixed per level)
```
Stored in `evidence.chain` with IDs pointing to measurements and answers.

---

## 4. Phases (STOP after each; report numbers)

### P0. Skeleton + configs + tests (½ day)
- Create the layout (§2), the JSON schema, the YAML configs with the DRAFT values above, the rule engine with its fixed
  condition functions, and the reasoning chain.
- `tests/triage/`:
  - one test per rule, plus edge cases: exactly at the boundary, at boundary ± margin, missing value, low quality, conflicting
    answers, repeat disagreeing;
  - red flag plus normal vitals → URGENT;
  - exercise + borderline → REMEASURE then a decision.
- **Done when:** `pytest tests/triage` passes and 100% of the rules are covered. **STOP** (print the rule-coverage table).

### P1. Measurement agents (reuse the Phase M extractors; 1–2 days)
- `hr_rppg.py`: POS/CHROM HR from the rest segment (60–120 s). Repeat reading after 60 s. Quality = SNR + POS/CHROM
  agreement.
- `thermal_vitals.py`:
  - **inner-canthus temperature** (max over a small canthus ROI; per Zhou 2020) with a calibration offset fitted against a
    contact thermometer (§6);
  - **breathing rate** from the nostril-ROI temperature oscillation (band 0.1–0.7 Hz);
  - quality = tracking confidence + ambient-temperature check.
- `devices.py`: optional BP cuff / clip oximeter readings (manual entry or serial/BLE), marked `source:"device"`.
- **Done when:** each agent returns value ± margin + quality on recorded test clips. **STOP.**

### P2. Questionnaire + session flow (1 day)
- `questionnaire.py`:
  - fixed items from `questionnaire.yaml`: red flags (chest pain, severe breathlessness, fainting, confusion, sudden
    weakness/numbness, severe headache, self-harm), context (exercise, caffeine, feeling ill, athlete), symptom duration,
    PHQ-2, GAD-2;
  - check the PHQ/GAD terms of use and cite Kroenke et al.
- The LLM may **rephrase** a question and **map a free-text answer** to one of the fixed options, but the user must confirm
  the mapped option ("So: no chest pain, correct?"). Unconfirmed → ask with buttons.
- `session.py` orchestration:
  consent → camera/thermal quality check → rest measurement (2 min) → questions → (REMEASURE if needed) → rule engine → chain
  → explanation → follow-up Q&A.
- **Done when:** 20 scripted sessions (synthetic inputs) produce the expected levels and chains. **STOP.**

### P3. Explainer, verifier, follow-up Q&A (reuse Approach A §8; 1–2 days)
- `explainer.py`:
  - one local Ollama call (`qwen2.5:3b-instruct`, temperature 0, JSON schema);
  - output `{summary, reasons[{id,text}], uncertainty, next_step}`;
  - numbers only as placeholders `{M1.value}`;
  - the level, the fixed advice line and the disclaimer are inserted by code.
- `verify.py`:
  - all placeholders are valid; no literal digits;
  - every fired-rule reason is mentioned;
  - the stated level wording matches the level;
  - no forbidden terms (diagnosis/disorder names, drug names, dosing, "you don't need a doctor");
  - the crisis text is present when R02 fired.
  On failure: retry once with the error text, then use the **deterministic template** (`render_template`, always complete).
- `followup_qa.py`:
  - answers only from the session record + `knowledge/triage_knowledge.md` (retrieve by section headings; no web);
  - out of scope (medication, diagnosis, "should I ignore this") → a fixed refusal + "please ask a doctor";
  - the verifier is applied to every answer.
- **Done when:** the X1-style metrics (below, Layer 3) pass on 200 synthetic sessions. **STOP.**

### P4. Vignette benchmark (the core decision test; 2–3 days + clinician time)
1. `vignettes.py`: a YAML vignette format (vitals with errors, answers, context, expected level, rationale).
2. Write about **120 vignettes**:
   - **60 URGENT** (enough for a lower 95% bound of about 0.95 if all are correct);
   - 30 SEE A DOCTOR SOON;
   - 25 SELF-CARE;
   - 5–10 RETAKE.
   Include borderline values (±margin), conflicts (high HR after exercise; normal vitals + red flag), missing values and
   contradictory answers.
3. **Reference labels:** 2–3 clinicians label each vignette independently (blind to the rules); disagreements are resolved by
   consensus. Export a labelling sheet (`results/triage/vignette_labels_template.xlsx`). Report inter-clinician weighted kappa.
4. Add the **published vignette sets** (Semigran 2015 BMJ; Schmieding 2022 JMIR; Hill 2020 MJA; from their supplements,
   checking the reuse terms) as an external set. Map their triage categories to our levels with a documented table.
5. Run the system and the **baselines** (§5) on all vignettes.
- **Done when:** the decision metrics table (§5.2) for own and published vignettes. **STOP** (send to the clinician with
  the confusion matrices).

### P5. Real-case benchmark on ED data (2–3 days)
**Open data first:** MIMIC-IV-ED **Demo** (100 patients) to build `mimic_ed.py`.
1. **Mapping** (`mimic_ed.py`, `yale.py`). Map each ED visit to an evidence record:
   - `triage.heartrate` → HR, `resprate` → RR, `temperature` → temperature (convert units; check °F/°C), `o2sat`, `sbp`/`dbp`
     only in the "with devices" arm;
   - `chiefcomplaint` → red-flag items via the clinician-reviewed regex dictionary in `red_flags.yaml`. Report the share of
     visits whose complaint maps to nothing.
   - **Add kiosk measurement error:** perturb HR, RR and temperature with the measured Layer-1 error distributions (10
     random draws). This gives "kiosk-like" inputs.
   - Context answers and PHQ/GAD are **not available** → those rules are inactive; say so.
2. **Reference outcome:** "urgent" = ESI acuity 1–2, **or** admitted to ICU / died in hospital within 48 h where linkable
   (sensitivity analyses: ESI only; disposition only). "Not urgent" = ESI 4–5 and discharged home.
3. **Splits:** MIMIC-IV-ED → 20% **dev** (rule tuning, only with clinician approval) and 80% **test**, by subject and by
   time (later years = test). The **Yale ED** data is the **external** test, never used for tuning. **KTAS** gives the
   human nurse under/over-triage rates as context.
4. **MIETIC** and **MIMIC-IV-Ext-CDS**: run the same mapping on their curated cases; CDS is used for the SEE A DOCTOR vs
   SELF-CARE boundary.
5. Arms:
   - (a) kiosk vitals only (HR, RR, temperature) + red flags;
   - (b) + BP/SpO2 devices;
   - (c) vitals only, no red flags;
   - (d) red flags only.
- **Done when:** the §5.2 table per dataset and arm, with exact CIs, plus the unmapped-complaint share. **STOP.**

### P6. Measurement benchmark (Layer 1; parallel with P4–P5)
- `measurement_bench.py`:
  - HR: UBFC-rPPG, PURE, MCD-rPPG (rest and post-exercise), UBFC-Phys T1;
  - breathing: BIDMC (PPG-derived) and AIVA if it has a reference;
  - thermal: AIVA (tracking), **own calibration session** (≥ 15 people: thermal canthus vs contact thermometer, rest +
    after coming in from outside);
  - vitals algorithms: VitalDB numerics;
  - M3PD only if its documentation shows video or PPG with reference ECG.
- Metrics: MAE, RMSE, Bland–Altman bias ± LoA, % within ±5 bpm / ±2 breaths / ±0.5 °C, quality pass rate, test–retest
  ICC.
- **Output feeds back:** the error margins in `vital_ranges.yaml` = the measured 95% absolute error per device. **STOP.**

### P7. Integration with the cognitive-load system (optional Level 2; 1 day)
- After the triage result, an **optional** "stress response today" module (2 min task + 1 min recovery) reuses the Approach
  A agents/fusion and shows a separate wellness panel.
- Hard rule (tested): the module's output is written to `evidence.wellness` and is **never read by `rules_engine.py`**.
- **Done when:** a test proves that changing `evidence.wellness` never changes the level. **STOP.**

### P8. Kiosk app + logging (1–2 days)
- `kiosk_app.py` (Streamlit, local, offline-capable): consent screen → live quality indicator → measurement countdown →
  question buttons → result card (level, reasons, next step, disclaimer, contacts) → follow-up chat → end.
- Logging: no names; a session ID only; save the evidence record + chain + text + timings to `results/triage/sessions/`
  (local).
- Timeouts: if the LLM takes more than the budget (config, e.g. 10 s), show the deterministic template.
- **Done when:** 10 end-to-end runs on the Mac, with latency p50/p95 recorded. **STOP.**

### P9. Clinician review pack + user tests + pilot (with ethics approval)
1. `scripts/export_review_pack.py`: rules, ranges, red flags, wording, knowledge text, 40 example sessions (borderline,
   conflicts, each level), the vignette and ED results. The clinician approves or edits → `status: approved` +
   `reviewed_by` + date.
2. **User understanding test** (scenario-based, ~20 people): show 12 result cards; ask "what would you do now?"; report the
   correct-action rate, especially for URGENT.
3. **Pilot** (~30 people, ethics-approved): full kiosk session + a clinician reviewing each record ("would you advise a
   doctor visit?"). Report agreement, the over-referral rate, retake rate, test–retest decision kappa (second session after
   10 min), and latency. With few positives this mainly estimates specificity; sensitivity comes from P4/P5.

---

## 5. Benchmark specification (Layers 2–4)

### 5.1 Baselines on every decision test (vignettes, MIMIC-IV-ED, Yale, MIETIC, CDS)
| Code | Baseline |
|---|---|
| D0 | always refer (SEE A DOCTOR for everyone) |
| D1 | vitals-only rules (no questionnaire) |
| D2 | red-flags-only rules (no sensors) |
| D3 | NEWS2-style aggregate score with published bands as a **reference** (hospital-validated, not kiosk-validated; say so) |
| D4 | **LLM alone**: local Qwen given the same case text, asked for the level (no rules). Never an external API for MIMIC |
| D5 | (check only) shallow decision tree, depth ≤ 3, fitted on the MIMIC dev split; used to suggest thresholds to the clinician, never deployed |
| **SYS** | our rule engine (and the full system with REMEASURE logic on vignettes) |

### 5.2 Decision metrics (per dataset × arm × baseline)
- **URGENT sensitivity** with an exact Clopper–Pearson 95% CI (primary).
- **Under-triage rate** (any case assigned a lower level than the reference) and **over-triage rate**.
- 4×4 confusion matrix; weighted kappa vs the reference (+ the inter-clinician kappa as the ceiling for vignettes).
- For ED data: sensitivity/specificity of URGENT vs the reference outcome; the share of urgent cases with **all kiosk vitals
  normal** (this shows why the red-flag questions are needed).
- Stratified by age group and sex where available (report subgroups with n ≥ 30).
- Paired comparison SYS vs each baseline on the same cases: McNemar for urgent misses, bootstrap CI for the
  sensitivity difference (resampling cases; for ED data, resampling patients).

### 5.3 Reasoning metrics (Layer 3)
- verifier pass rate (first try / final); template fallback rate;
- stated rule = fired rule (must be 100% after verification);
- numbers matching the record (100%);
- **swap tests**: change one input across a boundary → the level and the reasons change accordingly (% correct);
- conflict scenarios: the explanation names the conflict and its resolution (%);
- follow-up Q&A on 50 standard questions: grounded-answer %, correct-refusal % for out-of-scope;
- forbidden-term rate (must be 0);
- clinician rating of 40 sessions (safety, correctness, clarity; Likert; Krippendorff's α).

### 5.4 System metrics (Layer 4)
- time to result and time to explanation (p50/p95);
- retake rate; REMEASURE rate;
- test–retest decision kappa;
- offline operation check; behaviour on LLM timeout.

### 5.5 Report: `results/triage/REPORT.md`
Tables:
1. measurement accuracy;
2. own vignettes (SYS vs D0–D5);
3. published vignettes (SYS vs D0–D4, plus the published symptom-checker accuracy as context);
4. MIMIC-IV-ED test, arms a–d;
5. Yale external;
6. MIETIC / CDS;
7. reasoning;
8. system;
9. pilot.

Each with n, CIs and caveats:
- ED populations overstate urgency;
- the kiosk cannot measure BP/SpO2 without devices;
- context and PHQ/GAD rules are untested on ED data;
- the decision rules are clinician-reviewed but not clinically validated for deployment.

---

## 6. Order, stop points and time (8 GB Mac)

| Step | Depends on | Time |
|---|---|---|
| P0 skeleton + tests | — | ½ day |
| P1 measurement agents | Phase M extractors | 1–2 days |
| P2 questionnaire + session | P0 | 1 day |
| P3 explainer + verifier + Q&A | P0, Approach A §8 | 1–2 days |
| P6 measurement benchmark | P1; held rPPG data; calibration session | parallel, 2–3 days |
| P4 vignettes | P0–P3; clinician labels | 2–3 days + clinician |
| P5 ED benchmark | P0; MIMIC data use agreements signed; Yale download | 2–3 days |
| P7 Level-2 integration | Approach A | 1 day |
| P8 kiosk app | P1–P3 | 1–2 days |
| P9 review pack, user test, pilot | all; ethics approval | weeks (people time) |

**Team actions before starting:**
- sign the PhysioNet data use agreements for `mimic-iv-ed`, `mietic`, `mimic-iv-ext-cds` with the existing credential;
- download the Yale data (Zenodo 1308993) and the KTAS supplement;
- recruit 1 clinician for rules/vignettes/review (plus 1–2 more for vignette labels);
- verify the emergency and crisis numbers;
- book a contact thermometer, chest strap and (optionally) a BP cuff and clip oximeter for P6.
