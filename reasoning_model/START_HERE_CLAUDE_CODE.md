# START HERE: step-by-step runbook for Claude Code (setup → training → reasoning → own data)

This is the one file to give Claude Code first. It says **what to do, in what order, with which commands**, and when to stop
and show results. The detailed design is in the other briefs in this folder; Claude Code must read them when a step says so.

| File in `~/Documents/reasoning_model/` | What it is |
|---|---|
| `START_HERE_CLAUDE_CODE.md` | **This runbook (follow it top to bottom)** |
| `CLAUDE.md` | Original project brief (pipeline, rules) |
| `CLAUDE_CODE_APPROACH_A.md` | Design of the system being built (sections §1–§13 referenced below) |
| `CLAUDE_CODE_REASONING_FIX.md` | Detailed reference for findings / conflict / screening |
| `CLAUDE_CODE_TRIAGE_PIPELINE.md` | **Triage track**: guided 'see a doctor or not' agent (rules decide, LLM explains), MIMIC-IV-ED / vignette benchmarks, kiosk app |
| `TRIAGE_AGENT_EVIDENCE_AND_DATASETS.md` | Papers and datasets for the triage track |
| `NEXT_STEPS_AFTER_PHASE_M.md` | **Current next steps** (N1–N9) after the Phase M benchmark, plus team actions |
| `CLAUDE_CODE_DATASETS_TRAIN_TEST_BENCHMARK.md` | **Phase M (all-in-one)**: open datasets, download plan, per-modality training, testing protocols and benchmarking |
| `CLAUDE_CODE_MODALITY_TRAINING.md` | Older Phase M brief (superseded by the all-in-one file) |
| `CLAUDE_CODE_REVIEW_TASKS.md` + `results/review/REPORT.md` | The validity review already done (E1–E12) |
| `papers/` | Reference papers (ConSensus = base architecture) + `00_README_papers.md` |

---

## How to use this file (for the human)

1. Open the repo folder in Antigravity, then start Claude Code in it.
2. Paste the **"Paste to Claude Code"** block of the current phase. Wait until it reports back at a **STOP** point.
3. Check the reported numbers against the **"Done when"** list, then paste the next phase.
4. Long training runs: let Claude Code start them in the background with a log file, keep the Mac plugged in, and
   don't close the lid.

---

## Phase 0: machine setup (≈ 30 min)

**Paste to Claude Code:**
> Read `START_HERE_CLAUDE_CODE.md`, `CLAUDE.md` and `CLAUDE_CODE_APPROACH_A.md` fully. Then do Phase 0 of the runbook only:
> check the machine, set up the Python environment and Ollama, and report what you found. Do not train anything yet.

**Claude Code does:**
```sh
# 1. machine facts (report them)
sysctl hw.memsize hw.ncpu; sw_vers; df -h ~ | tail -1
# 2. repo + branch
cd ~/Documents && [ -d health-screening ] || git clone https://github.com/hima1323/health-screening.git
cd health-screening && git checkout reasoning-model && cd reasoning_model
# 3. Python 3.12 venv (not 3.13/3.14: the pinned wheels are tested on 3.12)
python3.12 -m venv .venv && .venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt statsmodels pyyaml openpyxl pytest
.venv/bin/python -c "import lightgbm, shap, neurokit2, pandas, pyarrow; print('ok', pandas.__version__, pyarrow.__version__)"
# 4. Ollama + model (only needed from Phase 6; install now)
brew install ollama            # skip if present
ollama serve > /tmp/ollama.log 2>&1 &
ollama pull qwen2.5:3b-instruct
# 5. copy the briefs and papers into the repo folder if they are not there yet
ls ~/Documents/reasoning_model/*.md ~/Documents/reasoning_model/papers
```
**Rules Claude Code must keep for the whole project:**
- Never write the ADABase password anywhere; the human exports it in the shell (`export ADABASE_PASSWORD=...`).
- The repo is public: never commit `data/` or `results/`, and add no co-author lines to commit messages.
- 8 GB RAM: at most `n_jobs=6`; read raw data one subject and one segment at a time; stop Ollama while training models
  (`pkill -f "ollama serve"`) and restart it for the LLM phases.
- Long jobs run in the background with a log and with sleep prevention:
  `caffeinate -i nohup .venv/bin/python <script> ... > results/logs/<name>.log 2>&1 &`.
  Check progress with `tail -f`.
- After unpacking any tar made on macOS, delete `._*` files: `find . -name '._*' -delete`. They break `train.load()`.

**Done when:** the Python import check prints `ok`; `ollama list` shows `qwen2.5:3b-instruct`; free disk is reported.
**STOP.**

---

## Phase 1: get the data in place (≈ 1–6 h, mostly downloading)

**Paste to Claude Code:**
> Do Phase 1 of the runbook. Prefer restoring features from `review_input.tar.gz` if I give it to you; otherwise
> download the raw ADABase files one subject at a time. Report the number of subjects, windows per task and free disk.

**Option A (fast): restore from the first laptop.** The human copies `review_input.tar.gz` into `reasoning_model/`:
```sh
tar xzf review_input.tar.gz && find . -name '._*' -delete
ls data/features | wc -l          # expect 30
```
**Option B: rebuild from raw (about 0.9 GB per subject, 2–12 min each).**
```sh
export ADABASE_PASSWORD=...        # typed by the human, never saved
caffeinate -i nohup .venv/bin/python src/features.py --all > results/logs/features.log 2>&1 &
# keep raw files if the disk allows (Phase 2 needs them again for k-drive baselines and 60 s windows);
# otherwise use --delete-raw and re-download per subject later
```
Also restore or rebuild the review tables (`results/review/windows.parquet`, `oof.parquet`, `segments/`). They are in the
hand-off zip.

**Done when:** 30 feature files; window counts printed per task and level (n-back ≈ 1138 test windows, k-drive 1710);
no subject missing without a stated reason. **STOP.**

---

## Phase 2: fix the inputs (preconditions) and re-extract features (≈ ½ day)

Read `CLAUDE_CODE_APPROACH_A.md` §2.

**Paste to Claude Code:**
> Do Phase 2 of the runbook (Approach A §2). Put new code in `src/approach_a/` and create the configs. Show me the diff
> before you change any existing file in `src/`.

**Claude Code does:**
1. Creates `configs/adabase.yaml`, which lists:
   - modalities and their features;
   - families: contactless {eye, AU}, cardiac {ECG, PPG}, autonomic {EDA, SKT, RSP, EMG};
   - labels: n-back low = 1-back, high = 2/3-back; k-drive low = level 1, high = levels 2–3;
   - window lengths: 30 s for eye/AU, 60 s with a 30 s step for contact signals;
   - the normalisation scheme.
2. `src/approach_a/normalise.py`: **kiosk-compatible normalisation.**
   - Centre on the last 60 s of the stimulus-matched baseline: baseline 2 for n-back, and k-drive baseline 2/3 (see
     `src/review/extract_kd_baselines.py`).
   - Scale by a fixed SD pooled over the **training subjects of each fold**.
   - No per-session SD.
3. `src/approach_a/hr_consensus.py`: per window, compare ECG-HR with PPG-HR. If they differ by more than 10 bpm, set both
   modalities' quality to below 0.5 for that window. Log the share of windows affected (≈ 13% expected).
4. Re-extract the contact features on 60 s windows **from the signal** (not by averaging 30 s features). Output:
   `data/features_a/<subject>.parquet`.
5. A sanity script `src/approach_a/check_features.py`:
   - no NaN explosion;
   - per-subject z ranges (flag |z| > 10);
   - ECG–PPG HR agreement;
   - the positive control: baseline vs any task, HR AUROC (expect > 0.8; if not, report a feature bug before going on).

**Done when:** features exist for 30 subjects; the positive control passes; the HR-consensus share is reported. **STOP.**

---

## Phase 3: TRAINING the predictor (agents + fusion), ≈ 3–6 h CPU, run overnight

This is the core training. Read `CLAUDE.md` §5 and Approach A §4.

**Paste to Claude Code:**
> Do Phase 3 of the runbook: train the per-modality LightGBM agents and the logistic fusion with the full LOSO protocol,
> seeds 0–4, in the background with logs. Stop Ollama first. When finished, give me the P1 comparison table.

**Training protocol (all of it inside leave-one-subject-out; the test subject is never seen during fitting):**
```
for each outer fold (1 test subject, 29 training subjects):
    for each modality agent m (ecg, ppg, eda, rsp, emg, skt, eye, au):
        inner 5-fold subject-wise CV on the 29 training subjects:
            Optuna, 25 trials, objective = inner per-subject AUROC
            search: num_leaves 7–31, learning_rate 0.01–0.1, min_child_samples 10–50,
                    feature_fraction 0.5–1.0, lambda_l2 0–10;  balanced class weights;
                    early stopping on the inner validation fold (patience 50, max 500 trees)
            -> best params, tree count = median best iteration over the 5 inner folds
            -> inner out-of-fold P(high) for every training window
        isotonic calibration fitted on the inner OOF P(high)
        refit the agent on all 29 subjects with the best params and tree count; apply calibration
        30% whole-modality dropout during training (the agent sees "missing" inputs as NaN)
    fusion: non-negative logistic regression on the inner-OOF agent logits + availability flags (29 subjects)
    store: test-subject P(high) per agent and fused, contributions c_m vs training means,
           agent reliability (inner per-subject AUROC), SHAP values per agent
repeat for seeds 0-4 (seed changes Optuna sampler, dropout and LightGBM bagging)
```
**Commands** (Claude Code writes `src/approach_a/train_agents.py`, reusing `src/train.py` / `src/fusion.py` logic):
```sh
pkill -f "ollama serve" || true
mkdir -p results/approach_a results/logs
caffeinate -i nohup .venv/bin/python src/approach_a/train_agents.py --config configs/adabase.yaml \
    --seeds 0 1 2 3 4 --n-jobs 6 --optuna-trials 25 > results/logs/train_agents.log 2>&1 &
tail -f results/logs/train_agents.log          # prints fold k/30, agent, best AUROC, minutes elapsed
```
Make the script **resumable**: save each finished fold to `results/approach_a/folds/seed{s}_fold{k}.pkl` and skip it on
restart. If RAM goes above ~6 GB, set `--n-jobs 4`.

**Outputs:** `results/approach_a/oof_agents.parquet`, `fusion_contrib.parquet`, `agent_reliability.csv`, the fold models.

**P1 report (Claude Code prints this table):** per-subject AUROC [95% subject-bootstrap CI] for each agent, the fusion, the
contactless/contact ablations and the order-only baseline (0.748). Before (review run) vs after (Phase 2 inputs): paired
per-subject differences; seed SD; n-back and k-drive (k-drive now centred on its own baseline).

**Done when:**
- fusion n-back per-subject AUROC is reported with its CI (review value 0.871 on 30 subjects; a similar or better value is
  expected);
- k-drive transfer is reported (review: 0.82 with baseline-2 centring);
- seed SD < 0.01;
- no fold used its test subject anywhere (Claude Code states how it checked).
**STOP.**

---

## Phase 4: rule agents + uncertainty (≈ ½ day; minutes of CPU)

Read Approach A §3 and §4.3.

**Paste to Claude Code:**
> Do Phase 4: build the rule agents (ROC–Youden, 2-of-3 by default, fitted per LOSO fold on training subjects) and the
> uncertainty signals (margin, ratio, optional Mondrian split-conformal). Run R1 and U1 and report.

```sh
.venv/bin/python src/approach_a/rule_agents.py --config configs/adabase.yaml      # -> rules per fold + R1 table
.venv/bin/python src/approach_a/fusion_uncertainty.py --alpha 0.1                 # -> margin, R, conformal sets + U1
.venv/bin/pytest tests/approach_a -q
```
**Done when:**
- R1: per-modality rule accuracy vs LightGBM agent, agreement rate, and fusion accuracy when the rule agrees vs disagrees;
- U1: accuracy of certain vs uncertain windows for each signal, the share flagged, and per-subject conformal coverage
  (about 90%).
Claude Code states which uncertainty signals it will use in Phase 5. **STOP.**

---

## Phase 5: reasoning layer in code (findings, conflict verdict, screening decision), ≈ 1 day

Read Approach A §5–§7 (details in `CLAUDE_CODE_REASONING_FIX.md`).

**Paste to Claude Code:**
> Do Phase 5: write `knowledge/feature_meaning.json` (leave references empty unless they come from the verified list),
> then agent findings, the conflict verdict and the session screening decision, with unit tests. Run C1 and S1 and print
> one example per verdict and per decision.

```sh
.venv/bin/python src/approach_a/agent_findings.py --all
.venv/bin/python src/approach_a/conflict.py --all          # C1
.venv/bin/python src/approach_a/screening.py --all         # S1 (ADABase block = mock session)
.venv/bin/pytest tests/approach_a -q
```
**Done when:**
- unit tests pass, including window `0000-ACAA / block 3 / 15 s` → SPLIT (R = 2.13) with the eye `push_reason` set;
- C1: SPLIT accuracy is clearly below the other verdicts;
- S1: REFER precision, NPV, sensitivity and inconclusive/retake shares with CIs at both operating points (the first simple
  version gave 0.89 / 0.89 / 14% inconclusive).
**STOP** (I review the printed examples).

---

## Phase 6: LLM explainer + verifier (≈ 1 day + an overnight LLM run)

Read Approach A §8.

**Paste to Claude Code:**
> Do Phase 6: restart Ollama, build the explainer with placeholders and the verifier, freeze the prompt on the 150
> development windows, then run X1 on the 600 evaluation windows in the background.

```sh
OLLAMA_NUM_PARALLEL=2 ollama serve > /tmp/ollama.log 2>&1 &
.venv/bin/python src/approach_a/explainer.py --dev            # prompt iteration on dev windows only
caffeinate -i nohup .venv/bin/python src/approach_a/explainer.py --eval --n-per-subject 20 \
    > results/logs/explainer.log 2>&1 &
.venv/bin/python src/approach_a/explainer.py --metrics        # X1 table
```
**Done when:** first-try and final verifier failure; direction-lexicon agreement; decision agreement = 100%; conflict-mention
recall; forbidden-term rate = 0; the swap counterfactual; latency p50/p95. Compare with the deterministic text. **STOP.**

---

## Phase 7: comparison with a cut-down ConSensus (LLM agents vote), overnight

Read Approach A §10 and `papers/01_ConSensus…pdf` (Sections 3–4).

**Paste to Claude Code:**
> Do Phase 7: implement the cut-down ConSensus baseline (statistical / semantic / hybrid) on the same 600 windows, match
> the hybrid rule to the paper or its code if it differs from my approximation, and give me the paired comparison table.

```sh
caffeinate -i nohup .venv/bin/python src/approach_a/consensus_lite.py --n-per-subject 20 \
    > results/logs/consensus_lite.log 2>&1 &
.venv/bin/python src/approach_a/consensus_lite.py --compare
```
**Done when:** balanced accuracy, AUROC, LLM calls, latency and schema failures per variant, plus the paired per-subject
difference against the Approach A fusion. Claude Code applies the decision rule in §10. **STOP.**

---

## Phase 8 (optional): LoRA on silver labels, only if X1 final failure is > 2% or latency is too high

Read Approach A §9. MLX on Apple Silicon only.
```sh
pkill -f "ollama serve"
.venv/bin/python src/approach_a/lora.py --build      # pairs = evidence prompt -> deterministic text, training subjects only
caffeinate -i .venv/bin/python src/approach_a/lora.py --train --folds 5   # subject-wise; rank 8-16, lr 1e-4, 2-3 epochs
.venv/bin/python src/approach_a/lora.py --compare    # same prompt/schema/decoding for base and LoRA
```
Adopt only if it beats the base model on X1 and is not worse than the deterministic text.

---

## Phase 9: report + small human check

**Paste to Claude Code:**
> Do Phase 9: write `results/approach_a/REPORT.md` (each experiment: hypothesis, numbers with CIs, figure, verdict; then
> claims we can and cannot make), and prepare the 40-window + 10-session human rating sheet (two versions, blinded) as a
> CSV and an HTML form.

The human study needs 3 raters who did not build the system (the team's friends, not the two authors). Claude Code
computes Krippendorff's α afterwards.

---

## Phase M: per-modality training on open datasets (run in parallel with Phases 3–9)

**Paste to Claude Code:**
> Read `CLAUDE_CODE_DATASETS_TRAIN_TEST_BENCHMARK.md` and follow its §10 order, stopping at each STOP point.
> Download one subject at a time and delete the raw files after extracting the measurements.

---

## Phase T: triage track (can run in parallel with Phase M / next steps)

**Paste to Claude Code:**
> Read `CLAUDE_CODE_TRIAGE_PIPELINE.md` (and `TRIAGE_AGENT_EVIDENCE_AND_DATASETS.md`) and do P0 first, stopping at each STOP point.
> Keep MIMIC data on this machine only and never send it to any external service.

---

## Phase 10: our own four-sensor recordings (rPPG + thermal + ECG + EEG)

Read Approach A §12. Do this phase only once recordings exist.

1. **Recording checklist** (the team, before data collection):
   - 30 completers (recruit about 35);
   - a Williams Latin-square order for the 0/1/2/3-back blocks, with silent responses;
   - 3-min blocks with a 60 s rest before each block (this rest is the baseline the kiosk can also record);
   - the stress block last;
   - RTLX + Paas ratings after each block;
   - a per-participant screening questionnaire (PSS-10 or the DASS-21 stress subscale);
   - Lab Streaming Layer sync plus an LED/TTL marker;
   - camera with fixed exposure; thermal camera after 10–15 min of acclimatisation;
   - EEG with Fz/Cz/Pz.
2. **Validate the single-sensor pieces on our data first:** rPPG HR vs ECG HR (MAE, Bland–Altman, per subject); EEG
   artefact rejection rate; thermal ROI tracking confidence.
3. `configs/own_study.yaml`: the rPPG / thermal / ECG / EEG agents (features, literature directions, quality indices from
   Approach A §12). Families: contactless {rPPG, thermal, (eye, AU)}, cardiac {ECG}, cortical {EEG}.
4. Re-run Phases 2–7 with `--config configs/own_study.yaml`; no code changes should be needed.
5. Report the session screening decision against the questionnaire target as a **feasibility estimate** (wide CIs with
   about 30 people).

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| `ArrowKeyError` / `read_parquet` crashes | pandas/pyarrow mismatch: reinstall the pinned versions from `requirements.txt` in the venv |
| `train.load()` fails on odd files | delete macOS `._*` files |
| RAM above 6 GB or the Mac freezes | `--n-jobs 4`; stop Ollama; process one subject at a time |
| A run was interrupted | rerun the same command; finished folds are skipped (resumable) |
| Ollama is slow or times out | `OLLAMA_NUM_PARALLEL=1`, keep `keep_alive=30m`; the kiosk falls back to the deterministic text |
| Positive control (rest vs task HR) < 0.8 | feature bug: inspect R-peak detection on 3 subjects before training |
| A number seems too good | check the order-only baseline (0.748) and that no fold used its test subject |
