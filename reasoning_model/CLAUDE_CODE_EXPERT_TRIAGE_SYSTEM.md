# Master brief for Claude Code: build the hybrid expert (rule-based) triage system, end to end

## How to start (paste this into Claude Code)
> Read `triage_starter_kit/CLAUDE_CODE_EXPERT_TRIAGE_SYSTEM.md` fully, then `START_HERE_CLAUDE_CODE.md` (project rules) and
> `TRIAGE_AGENT_EVIDENCE_AND_DATASETS.md`. Do phase E0 only and stop. Keep all MIMIC data on this machine and never send it
> to any external service or online model. Show me a diff before changing any existing file in `src/`.

This file **supersedes** `CLAUDE_CODE_TRIAGE_PIPELINE.md` (keep that as a reference). It adds the rule-derivation phase and
ships with a **starter kit** of draft materials:
```
triage_starter_kit/
  CLAUDE_CODE_EXPERT_TRIAGE_SYSTEM.md      <- this file
  configs/triage/{vital_ranges,red_flags,questionnaire,rules,contacts}.yaml   (DRAFT)
  evidence/evidence_table.csv              (sources, thresholds, reported performance, reliability, kiosk caveats)
  knowledge/triage_knowledge_DRAFT.md      (plain-language text the explainer may use; DRAFT)
  templates/{vignette_template.yaml, delphi_round_form.csv, rule_provenance_card.yaml, clinician_review_checklist.md}
```

---

## 1. What the system is

A **hybrid knowledge-based (neuro-symbolic) triage system** for a self-service health kiosk:

| Layer | Type | Job |
|---|---|---|
| Perception | signal processing / ML | rPPG heart rate, thermal temperature (inner canthus) and breathing rate, optional BP cuff and clip oximeter; a quality score per reading |
| Questionnaire | fixed items | red-flag symptoms, context (exercise, caffeine, feeling unwell, athlete), symptom duration, PHQ-2, GAD-2 |
| **Decision** | **expert system** (ordered, clinician-reviewed rules) | URGENT / SEE A DOCTOR SOON / SELF-CARE & MONITOR / RETAKE (plus internal REMEASURE, NOT_SUITABLE) |
| Reasoning | code | evidence → interpretation → context → rule fired → uncertainty → advice |
| Language | local LLM (Ollama qwen2.5:3b) + verifier | explains the chain, answers follow-up questions from the record + approved knowledge text only |
| Optional wellness | Approach A cognitive-load agents | "stress response today" panel; **never read by the rule engine** |

## 2. Non-negotiable safety and compliance rules
1. Only the rule engine decides. No ML or LLM output can set or change the level.
2. Every rule, range, red flag and message is **DRAFT** until a clinician approves it (`status: approved`, `reviewed_by`,
   `review_date`). `kiosk_app.py` refuses to start a user session while anything is DRAFT, except in `--demo` mode with
   synthetic data.
3. Red-flag symptoms override every sensor value. When in doubt, refer. Borderline → re-measure, never ignore.
4. Never output "you don't need a doctor". Use the fixed SELF-CARE message from `rules.yaml`.
5. No diagnoses, disorder names, medication or dosing advice in generated text (verifier-enforced).
6. A positive self-harm item → URGENT + crisis contacts from `contacts.yaml` (the team verifies the numbers).
7. **MIMIC data use agreements:**
   - `data/restricted/` only (git-ignored);
   - never sent to an external API or online LLM;
   - aggregate results only in `results/`;
   - access holder recorded in `data/restricted/README_ACCESS.md`.
8. Research / wellness prototype under ethics approval; not a medical device. Disclaimer on every result screen.
9. Project rules: 8 GB RAM; `n_jobs ≤ 6`; never commit `data/` or `results/`; no secrets in files.

## 3. Code layout
```
configs/triage/*.yaml               # copied from the starter kit, then edited only via reviewed changes
evidence/evidence_table.csv          knowledge/triage_knowledge.md (approved copy of the DRAFT)
src/triage/
  schema.py            # pydantic models + JSON schema for every YAML and the evidence record
  measure/hr_rppg.py  measure/thermal_vitals.py  measure/devices.py
  questionnaire.py  evidence.py  rules_engine.py  reasoning_chain.py
  explainer.py  verify.py  followup_qa.py  session.py  kiosk_app.py
  derive/                 # rule-derivation analyses (phase E1)
    source_check.py  mimic_dev_bands.py  nhanes_overreferral.py  rule_learning.py  delphi.py
  bench/                  # benchmarks (phases E5–E7)
    vignettes.py  mimic_ed.py  yale.py  mietic.py  cds.py  ktas.py  baselines.py  metrics.py  run_bench.py  measurement_bench.py
tests/triage/            results/triage/        data/restricted/…  data/public/…
```

---

## 4. Phases (STOP after each; report numbers and print examples)

### E0. Skeleton, starter-kit import, schema, rule engine, tests (½–1 day)
1. Copy the starter-kit `configs/triage/*`, `evidence/`, `knowledge/` and `templates/` into the project. Do not change
   values.
2. `schema.py`: validate every YAML against a schema (types, required provenance fields, ordered rules, `status`).
3. `rules_engine.py`: the rule conditions are a **fixed set of named functions**:
   - `any_answer_yes`, `answer`, `score`;
   - `any_quality_below`, `face_not_found`;
   - `any_outside(range_name, margin, confirmed_repeat)`;
   - comparisons on named measures.
   **No `eval` of strings.** Parse the `when:` expressions with a tiny safe parser restricted to those functions, or
   rewrite them as structured YAML.
4. `reasoning_chain.py` and `evidence.py` (the evidence-record schema in §6.1).
5. `tests/triage/`:
   - every rule fires on a minimal case and doesn't fire just below its condition;
   - boundaries at exactly the threshold and at threshold ± margin;
   - missing values; low quality; disagreeing repeats;
   - red flag + normal vitals → URGENT; self-harm → crisis contacts shown;
   - exercise + borderline → REMEASURE then decision;
   - `wellness` never changes the level (property test with random wellness values).
- **Done when:** `pytest tests/triage` passes, with 100% rule coverage (print the table). **STOP.**

### E1. Rule derivation: make the conditions evidence-based (2–4 days + clinician time)
**E1.1 Source check (`derive/source_check.py`)**
- For every row of `evidence/evidence_table.csv` and every number in `vital_ranges.yaml`, open the **official current
  document** where it is openly available:
  - the NEWS2 chart (Royal College of Physicians);
  - the ESI handbook (AHRQ / ENA);
  - NICE NG253 (sepsis, replaces NG51);
  - the PHQ/GAD official distribution.
- Record the document version, the page/section and the exact value in `evidence/source_check.csv`.
- **Flag every mismatch** between the starter kit and the source. The source wins; the change is noted for the clinician.
- Copy the **exact official wording** of PHQ-2 / GAD-2 items and response options into `questionnaire.yaml`, and check their
  terms of use.

**E1.2 MIMIC-IV-ED dev analysis (`derive/mimic_dev_bands.py`)**: needs the signed data use agreement; develop the code on
the open MIMIC-IV-ED Demo first.
1. Build the cohort:
   - adults 18–65 (also report > 65 separately);
   - first ED stay per subject in the dev split;
   - dev = a random 20% of subjects from the earlier years. Never touch the test split here.
2. Outcome "urgent" = ESI 1–2 **or** ICU admission / death within 48 h where linkable (also report each definition
   separately).
3. For HR, RR, temperature (°F→°C; check units), SpO2 and SBP: the urgent rate by value band (5 bpm / 2 breaths / 0.2 °C
   bins), overall and by age group, with Wilson CIs. Plot them with the draft normal and urgent cut-offs overlaid.
4. Add **kiosk measurement error** (from E5, or placeholders until E5 is done): perturb the vitals with the measured error
   distribution (10 draws). Report the sensitivity / false-positive rate of each draft cut-off with and without the error.
5. Chief complaint → red-flag mapping with `red_flags.yaml` regexes:
   - urgent rate per red flag;
   - the share of urgent visits with **no** red flag and **normal kiosk vitals** (the cases the kiosk would miss);
   - the share of unmapped complaints;
   - the top 50 unmapped complaints by frequency, for the clinician.

**E1.3 Healthy-population over-referral (`derive/nhanes_overreferral.py`)**
- From NHANES (open; check the exact examination files for pulse and blood pressure, and the survey weights), adults 18–65:
  the weighted % above/below each draft cut-off, by age and sex.
- This estimates how many ordinary kiosk users each rule would flag. Report it next to the MIMIC sensitivity for every
  cut-off (a sensitivity vs over-referral table).

**E1.4 Interpretable rule-learning suggestions (`derive/rule_learning.py`), dev split only**
- Features = **kiosk-measurable only** (HR, RR, temperature, red-flag indicators, age group), with kiosk error added.
- Models: `sklearn` decision tree (depth ≤ 3, class-weighted); rule lists via the `imodels` package (e.g. an optimal rule
  list / CORELS-type model and a Bayesian rule list; check the class names in the installed version); optional point score
  (`fasterrisk`).
- Output: each learned rule as plain text with its dev sensitivity/specificity, **compared with the draft rule it would
  change**. These are **suggestions only**, for the clinician.

**E1.5 Delphi consensus pack (`derive/delphi.py`)**
- Generate `results/triage/delphi_round1.xlsx` from `templates/delphi_round_form.csv`. One row per rule, containing:
  - the rule text and its sources;
  - the E1.2 and E1.3 numbers;
  - any E1.4 suggestion;
  - columns for agree / modify / remove and comments.
- 3–5 clinicians rate independently. Score: a rule is kept if ≥ 80% agree. Rules marked "modify" are rewritten and go to
  round 2 with anonymous group results. Stop after round 2 or 3.
- Store each rule's history in a **provenance card** (`templates/rule_provenance_card.yaml`) inside `rules.yaml`.

**E1.6 Lock:** set version v1.0, `status: approved`, reviewer and date for rules, ranges, red flags, messages and knowledge
text. From here on the rules are **frozen for testing**; any change = new version + re-test.
- **Done when:** the source-check table, the MIMIC dev plots/tables, the NHANES over-referral table, the rule-learning
  suggestions, the Delphi results and the locked v1.0 config. **STOP.**

### E2. Measurement agents (1–2 days; reuse the Phase M extractors)
- `hr_rppg.py`: POS/CHROM on a 60–120 s rest segment with MediaPipe skin ROI. Repeat reading after 60 s. Quality = SNR +
  POS/CHROM agreement.
- `thermal_vitals.py`:
  - inner-canthus temperature (high percentile of a small canthus ROI) + a calibration offset/slope fitted against a contact
    thermometer (from E5);
  - breathing rate from the nostril-ROI temperature oscillation (0.1–0.7 Hz);
  - quality = tracking confidence, head pose and ambient-temperature range.
- `devices.py`: optional cuff / oximeter values (manual entry or serial/BLE); `source: device`.
- Every reading: value, `error_margin` (from E5), quality, the source, and both repeat values.
- **Done when:** recorded test clips give values + quality. **STOP.**

### E3. Questionnaire and session orchestration (1 day)
- `questionnaire.py` from `questionnaire.yaml` (order: consent → red flags → context → duration → PHQ-2 → GAD-2).
- The LLM may rephrase a question and map free text to an option, but the **user confirms the mapped option**. If it is
  unconfirmed, use buttons.
- `session.py`:
  consent → scope check (age, pregnancy) → quality check → 2-min rest measurement → questions → REMEASURE (once, after 5 min)
  if R04 → rule engine → chain → explanation → follow-up Q&A → end.
- **Done when:** 20 scripted synthetic sessions give the expected level and chain. **STOP.**

### E4. Explainer, verifier, follow-up Q&A (1–2 days; reuse Approach A §8)
- `explainer.py`:
  - one Ollama call (temperature 0, JSON schema): `{summary, reasons[{id,text}], uncertainty, next_step}`;
  - numbers only as placeholders (`{M1.value}`, `{M1.unit}`);
  - the level text, fixed advice, disclaimer and crisis contacts are inserted by code.
- `verify.py`:
  - placeholders valid; no literal digits;
  - every fired-rule reason mentioned; level wording consistent;
  - no forbidden terms (disorder names, drug names, dosing, "you don't need a doctor");
  - crisis text present when R02 fired.
  Retry once with the error text, else use the deterministic template (`render_template`, always complete).
- `followup_qa.py`:
  - retrieve only from the session record + the **approved** `knowledge/triage_knowledge.md` (by section key);
  - out of scope → the fixed refusal;
  - every answer verified.
- Time budget: if the LLM takes longer than `config.llm_timeout_s` (e.g. 10 s), show the template.
- **Done when:** the Layer-3 metrics (§5.3) on 200 synthetic sessions. **STOP.**

### E5. Measurement benchmark (Layer 1; can run in parallel from E2)
- HR: UBFC-rPPG, PURE, MCD-rPPG (rest and post-exercise), UBFC-Phys T1; M3PD only if it has video + reference ECG/PPG.
- Breathing: BIDMC (PhysioNet, open) for pulse-derived breathing; AIVA if it has a breathing reference.
- Thermal: AIVA (tracking), plus an **own calibration session** (≥ 15 people; thermal canthus vs contact thermometer; at rest
  and after coming in from outside).
- VitalDB (open) to check the HR/RR algorithms against monitor numerics.
- Metrics: MAE, RMSE, Bland–Altman bias ± LoA, % within ±5 bpm / ±2 breaths / ±0.5 °C, quality pass rate, test–retest ICC.
- **Writes `error_margin` per measure** = the measured 95th percentile of absolute error. That value goes into
  `vital_ranges.yaml` (a reviewed change). **STOP.**

### E6. Vignette benchmark (Layer 2a; core decision test)
1. Clinicians write or approve about **120 vignettes** (template provided): **60 URGENT**, 30 SEE A DOCTOR SOON, 25 SELF-CARE,
   5–10 RETAKE. Include borderline values (± margin), conflicts (exercise + high HR; normal vitals + red flag), missing values
   and contradictory answers.
2. Labels: 2–3 clinicians independently, **blind to the rules**, then consensus. Report the inter-clinician weighted kappa.
3. Auto-generate **variants** (±1 margin around each threshold) for robustness checks. These are not used in headline
   metrics.
4. Add the **published vignette sets** (Semigran 2015 BMJ; Schmieding 2022 JMIR; Hill 2020 MJA; check their reuse terms)
   with a documented mapping of their triage categories to our levels.
- **Done when:** the §5.2 table for own and published vignettes, SYS vs D0–D5. **STOP.**

### E7. Real-case benchmark on ED data (Layer 2b)
- **Test split** of MIMIC-IV-ED (80% of subjects, later years; never used in E1).
- **Yale ED data** (Zenodo 1308993; open; external, never tuned).
- **MIETIC** (curated ESI cases) and **MIMIC-IV-Ext-CDS** (the referral / SEE-A-DOCTOR vs SELF-CARE boundary).
- **KTAS** (Moon 2019 PLoS ONE supplement) for human nurse under/over-triage as context.
- Arms:
  - (a) kiosk vitals (HR, RR, temperature with simulated kiosk error) + red flags;
  - (b) + BP/SpO2 devices;
  - (c) vitals only;
  - (d) red flags only.
- Context and PHQ/GAD rules are inactive on ED data. State this.
- **Done when:** the §5.2 tables per dataset × arm with exact CIs; the share of urgent cases the kiosk would miss and why.
  **STOP.**

### E8. Optional wellness integration (Approach A, 1 day)
- An optional 2-min task + 1-min recovery after the triage result; a separate "stress response today" panel written to
  `evidence.wellness`.
- A test proves the rule engine never reads it.

### E9. Kiosk app (1–2 days)
- `kiosk_app.py` (Streamlit, local, offline-capable):
  - consent;
  - live quality indicator;
  - measurement countdown;
  - question buttons;
  - result card (level, reasons, next step, disclaimer, contacts);
  - follow-up chat;
  - end screen.
- Anonymous session ID; local logs of evidence + chain + text + timings.
- `--demo` mode with synthetic inputs for presentations.

### E10. Clinician sign-off, user understanding test, pilot (needs ethics approval)
1. `scripts/export_review_pack.py`: configs, evidence table, source check, E1–E7 results, 40 example sessions,
   `templates/clinician_review_checklist.md`. The clinician signs; the versions are recorded.
2. **User understanding** (about 20 people, scenario cards): "what would you do now?" Report the correct-action %, with
   URGENT separately.
3. **Pilot** (about 30 people): a full session + a clinician reviewing each record ("would you advise a doctor visit?").
   Report agreement, over-referral, retake rate, test–retest decision kappa (repeat after 10 min) and latency. Sensitivity
   comes from E6/E7, not from the pilot.

---

## 5. Benchmark specification

### 5.1 Baselines (every decision test)
| Code | Baseline |
|---|---|
| D0 | always refer (SEE A DOCTOR) |
| D1 | vitals-only rules |
| D2 | red-flags-only rules |
| D3 | NEWS2-style aggregate from the official bands, as a hospital-validated reference (partial with kiosk vitals; say so) |
| D4 | **LLM alone**: local Qwen given the same case text, asked for the level; never an online model for MIMIC |
| D5 | the E1.4 learned tree / rule list (for comparison only; never deployed) |
| **SYS** | the locked rule engine (with REMEASURE logic on vignettes) |

### 5.2 Decision metrics
- **URGENT sensitivity** with an exact (Clopper–Pearson) 95% CI (primary). With 60 urgent vignettes all correct, the lower
  bound is about 0.95.
- Under-triage % (any case assigned below the reference) and over-triage %.
- 4×4 confusion matrix; weighted kappa vs the reference (the inter-clinician kappa as the ceiling).
- ED data: sensitivity / specificity of URGENT vs the outcome; the share of urgent cases with all kiosk vitals normal and no
  mapped red flag.
- Subgroups (age group, sex) when n ≥ 30.
- SYS vs baseline on the same cases: McNemar on urgent misses; bootstrap CI for the sensitivity difference (resampling
  patients).

### 5.3 Reasoning metrics
- verifier pass (first try / final), template fallback rate;
- stated rule = fired rule (100% after verification), numbers = record (100%);
- **swap tests** (move one input across a threshold → level and reasons change correctly);
- conflict scenarios explained (%);
- follow-up Q&A: 50 standard questions, grounded-answer %, correct-refusal %;
- forbidden-term rate = 0;
- clinician rating of 40 sessions (safety, correctness, clarity; Krippendorff's α).

### 5.4 System metrics
- time to result and to explanation (p50/p95);
- retake and REMEASURE rates;
- test–retest decision kappa;
- offline run; behaviour on LLM timeout.

### 5.5 Report: `results/triage/REPORT.md`
Tables:
1. source check;
2. MIMIC dev bands + NHANES over-referral;
3. rule-learning suggestions and the clinician decisions;
4. Delphi results;
5. measurement accuracy;
6. own vignettes;
7. published vignettes;
8. MIMIC-IV-ED test (arms a–d);
9. Yale external;
10. MIETIC / CDS;
11. reasoning;
12. system;
13. pilot.

Caveats to state:
- ED populations overstate urgency;
- the kiosk can't measure BP/SpO2 without devices;
- context/PHQ/GAD rules are untested on ED data;
- the system is clinician-reviewed but **not** clinically validated for deployment.

## 6. Data structures

### 6.1 Evidence record
```json
{"session_id":"…","versions":{"rules":"v1.0","ranges":"v1.0","red_flags":"v1.0","code":"<git sha>"},
 "scope":{"age":34,"pregnant":"no"},
 "measurements":[{"id":"M1","name":"heart_rate","value":108,"unit":"bpm","error_margin":3,"quality":0.92,
                  "repeat_values":[109,107],"source":"rppg"}],
 "answers":[{"id":"Q1","item":"chest_pain","answer":"no","confirmed":true}],
 "scores":[{"id":"S1","name":"PHQ2","value":1}],
 "decision":{"level":"SEE_DOCTOR_SOON","rule_id":"R07_vital_out","rule_version":"v1.0"},
 "chain":[{"step":"interpretation","refs":["M1"],"text_key":"heart_rate_high"}],
 "wellness":null}
```

### 6.2 Configs
The starter-kit YAMLs define the formats. Keep the provenance fields on every rule (`sources`, `data_check`,
`rule_learning_suggestion`, `delphi`, `version`, `status`, `reviewed_by`, `review_date`).

## 7. Evidence base (from `evidence/evidence_table.csv`; verify in E1.1)
| Source | Use | Reported performance (validated population) | Strength for this kiosk |
|---|---|---|---|
| NEWS / NEWS2 (RCP 2017; Smith 2013 *Resuscitation*) | urgent bands | AUROC 0.722 cardiac arrest, 0.857 ICU, 0.894 death within 24 h (hospital); ED: NEWS 0.904, NEWS2 0.901 | strong source, partial with kiosk vitals |
| ESI danger zone (AHRQ/ENA handbook; Tanabe 2003) | look-closer triggers; MIMIC/Yale label | inter-rater weighted kappa 0.69–0.87; single danger-zone vitals weakly predictive alone | moderate |
| NICE NG253 (2025, replaces NG51); qSOFA (Seymour 2016) | background for fever + fast breathing + confusion | qSOFA non-ICU AUROC 0.81; pooled sensitivity 0.51 / specificity 0.83 | low for screening |
| Red flags (Manchester Triage System, NICE CKS, ESI L1–2) | URGENT override | consensus; mistriage is common in triage systems (Zachariasse 2019) | high for sensitivity, depends on wording |
| PHQ-2 (Kroenke 2003; Levis 2020 *JAMA*) | talk to a professional | ≥ 3: sensitivity 0.72, specificity 0.85 | strong |
| GAD-2 (Kroenke 2007; Plummer 2016) | talk to a professional | AUC 0.80–0.91 | strong |
| Reference ranges (Nanchen 2018 *Heart*; Protsiv 2020 *eLife*; Zhou 2020, Ghassemi 2018 thermography) | normal bands; temperature method | convention; normal mean temperature < 37 °C; inner canthus best | convention; needs calibration + repeat |
| NHANES (CDC) | over-referral in healthy adults | descriptive | data |
| Semigran 2015 *BMJ* (+ Hill 2020, Schmieding 2022, Chambers 2019, Wallace 2022) | vignette benchmark design | published symptom-checker triage accuracy as context | method |
| LLM triage studies (Levine 2024, Williams 2024, Masanneck 2024, Fraser 2023) | why the LLM doesn't decide; D4 baseline | variable, inconsistent | context |

## 8. Team actions (humans)
1. Sign the PhysioNet data use agreements: `mimic-iv-ed`, `mietic`, `mimic-iv-ext-cds`.
2. Download the Yale data (Zenodo 1308993) and the KTAS supplement (Claude Code can download open files).
3. Recruit **1 lead clinician** (rules, Delphi, sign-off) plus **2–4 clinicians** (Delphi, vignette labels).
4. Verify the emergency and crisis numbers in `contacts.yaml`.
5. Arrange a contact thermometer, chest strap, optional BP cuff and clip oximeter, and the calibration session (E5).
6. Ethics approval before E10.

## 9. Order and time (8 GB Mac)
E0 (½–1 d) → E1 (2–4 d + clinician rounds) → E2 + E5 in parallel (2–3 d) → E3 (1 d) → E4 (1–2 d) → E6 (2–3 d + clinician
labels) → E7 (2–3 d) → E8 (1 d) → E9 (1–2 d) → E10 (weeks, people time).
