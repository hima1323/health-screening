# Explainable multimodal reasoning model: project brief

This file is the hand-off from the planning session. Read it fully before writing code.

## Goal
Build an explainable model that turns physiological signals into a conclusion (cognitive load / stress level) plus an evidence-cited explanation.
Architecture: **predictor decides, reasoner explains.**
1. Per-modality signal quality + features
2. LightGBM predictor (calibrated) + SHAP attributions
3. Evidence record (JSON) per window
4. Reasoning layer: rule table + small LLM that explains, never changes the label, and a verifier that rejects any number not in the evidence record

## Final target data
The final model needs rPPG, thermal, ECG and EEG **recorded together on the same people**. No public dataset has all four,
so the final model will be trained only on the team's own recordings. Public datasets are used only to pretrain or validate
single-modality steps. **Never merge samples from different datasets as if they were the same person.**

## Current stage: pilot on ADABase (build and debug the pipeline)
ADABase (Oppelt et al., Sensors 2023, doi 10.3390/s23010340). Data: `data/adabase/` (raw, read-only, not in git).
The share password is NOT stored here; pass it as `ADABASE_PASSWORD` for downloads.

### What the public release actually contains (verified 2026-10-12)
- **30 subjects** (not 51), one HDF5 per subject (~0.9 GB, ~27 GB total), PyTables blosc:lz4 (h5py cannot read it).
- `SIGNALS` table on a 1 ms grid, NaN-padded. ECG I/II, **PPG**, EDA, RSP, EMG, SKT stored at **1000 Hz** (the PDF's
  500/250/100 Hz are acquisition rates); eye tracker 250 Hz (gaps NaN); face ~25 Hz: 20 AU probabilities, 7 emotions,
  head pose, face score; MediaPipe body landmarks. Precomputed peak flags for ECG, PPG, RSP, EDA.
- **No raw face video -> no rPPG.** No EEG, no thermal.
- n-back test levels 1-6 = 1/2/3-back single task, then 1/2/3-back dual task (120 s each). k-drive test levels 1-3 (300 s).
  Baseline 1 = 5 min black screen (eye validity is low there). NASA-TLX per test level. Some subjects lack face data.
- All 138 float columns are stored as one block: never `pd.read_hdf(..., columns=...)` the whole file (~10 GB RAM);
  `load_adabase.Subject.read(start, stop)` reads one segment.

## Machine constraints
- macOS, 8 GB RAM, 8 CPU cores, **no GPU**, little free disk.
- Process one subject at a time: `python src/features.py --all --delete-raw` downloads, extracts, deletes the raw file.

## Pipeline (ADABase pilot)
```
src/load_adabase.py   # download + per-segment loader
src/quality.py        # per-window signal-quality indices
src/features.py       # 30 s / 15 s windows, NeuroKit2 features, baseline z-scores -> data/features/<subject>.parquet
src/train.py          # LightGBM LOSO + isotonic calibration + modality dropout + SHAP + k-drive cross-task
src/evidence.py       # per-window evidence JSON -> results/evidence/
src/reasoner.py       # rules + LLM (Ollama qwen2.5:3b-instruct) + verifier -> results/explanations/
src/evaluate.py       # metrics, ablations, calibration, faithfulness, reasoner stats -> results/*.csv, *.png
src/test_reasoner.py  # verifier self-check
```
1. **Labels.** n-back binary: low = 1-back, high = 2-back / 3-back (baseline 2 is the normalisation reference;
   with `--ref rest` it is also a low sample, as in the original brief); 3-class 1/2/3-back; raw NASA-TLX as
   a continuous target. **k-drive held out entirely** (level 1 low, 2-3 high) as the cross-task test set.
2. **Windows.** 30 s, 50% overlap, inside each run. Z-scores are added at load time (`features.zscore`): centre on
   baseline 2 (same stimulus, no task), scale by the subject's SD over all windows of that task. The black-screen
   baseline 1 gave pupil z ~ +5 (luminance) and |z| > 10 for EMG/rare AUs. `--ref rest` keeps the brief's version.
   k-drive baseline 2 was not extracted for the 30 subjects, so k-drive is centred on baseline 1.
3. **Features.** ECG HR/RMSSD/SDNN/pNN50 (no LF/HF: 30 s too short); PPG rate/amplitude/PTT; EDA tonic/SCR count/amp;
   RSP rate/depth/variability; EMG RMS; SKT mean/slope; pupil mean/slope, blink rate, fixation duration; AU activation rates.
   Quality per modality; a modality is masked when its quality < 0.5.
4. **Never use as inputs:** reaction time, accuracy, NASA-TLX or any label, accelerometer.
5. **Predictor.** LightGBM (num_leaves=15, lr=0.03, <=500 trees, early stopping, min_child_samples=20,
   feature_fraction=0.7, balanced classes), LOSO, 30% modality dropout. Inside each fold a 5-fold subject-wise inner
   CV gives the tree count, the Optuna objective (`--tune`, 25 trials) and out-of-fold probabilities for isotonic
   calibration. Reference: ADABase paper, n-back fused AUC 0.88 / F1 0.77 (51 subjects, 2-min windows, 10-fold).
6. **Ablations.** contactless (eye + AUs) vs contact vs all; leave-one-modality-out; single modality; majority class.
7. **Evidence record:** label, calibrated probability, top-6 SHAP features with raw value and z-score, rule directions, quality.
7b. **Modality agents + fusion** (`src/fusion.py`): one LightGBM agent per modality (calibrated P(high), SHAP over its
   own features; unavailable when missing / low quality), fused by a logistic regression with non-negative agent
   weights trained on inner out-of-fold agent outputs. Log-odds split exactly into per-agent contributions, which the
   reasoner cites (`--fusion`). New sensors (rPPG, thermal, EEG) = new agents, pretrainable on single-modality data.
8. **Reasoner.** JSON `{conclusion, confidence, evidence[], conflicts[], abstain}`, temperature 0; verifier checks label,
   confidence, feature names and every number; regenerate once, then abstain. Abstain is decided by rule
   (confidence < 0.6 or all cited modalities low quality) and passed to the LLM. Falls back to a template without Ollama.
   Setup: `brew install ollama && ollama serve & ollama pull qwen2.5:3b-instruct`.
9. **Evaluation.** Balanced accuracy, macro-F1, AUROC (LOSO); n-back -> k-drive; ECE; faithfulness (remove cited
   features, probability must drop more than for random ones); citation accuracy; hallucination rate.

## Test laptop hand-off
`run_pipeline.sh` ends by writing `results/handoff.tar.gz` (features, fold models, evidence, LoRA adapter, tables).
Unpack it into `reasoning_model/`, install `requirements.txt` (mlx/mlx-lm only on Apple Silicon), run Ollama, then
`python src/reasoner.py --subject <id> [--fusion]` and `python src/evaluate.py`.

## Later stages (not now)
- rPPG step validation on UBFC-rPPG, PURE, MPSC-rPPG, IMVIA-NIR (POS algorithm; HR MAE vs contact PPG).
- Pretrain encoders: EEG on MAHNOB-HCI (needs EULA), thermal on AIVA (Zenodo 14764535).
- Final four-modality model on the team's own recordings (rPPG + thermal + ECG + EEG).

## Rules
- Subject-wise splits only; report the number of subjects and windows in every result.
- Never print or commit passwords or credentials.
- Commit small, runnable steps; each script runnable as `python src/<name>.py --subject <id>`.
