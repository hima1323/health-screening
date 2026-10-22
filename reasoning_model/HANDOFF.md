# Hand-off: continue the ADABase review on a new laptop

For Claude Code on the second laptop. Read in this order: `CLAUDE.md` (project brief), this file,
then `CLAUDE_CODE_REVIEW_TASKS.md` (the task). This file only adds what the task brief can't know:
setup, where the data comes from, and the audit answers already found on the first laptop.

## 1. Setup

```sh
git clone https://github.com/hima1323/health-screening.git
cd health-screening && git checkout reasoning-model
cd reasoning_model
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # tested with Python 3.12.0
.venv/bin/pip install statsmodels                                         # needed for E1/E7 mixed models
```
- `mlx` / `mlx-lm` install only on Apple Silicon. On other machines remove those two lines from requirements;
  only the LoRA steps (E13) need them.
- Ollama is needed only from E11 on: `brew install ollama && ollama serve & ollama pull qwen2.5:3b-instruct`.
- Check the machine first (`sysctl hw.memsize hw.ncpu` on macOS, `nproc; free -g` on Linux). The task brief
  assumes 8 GB / 8 cores. If this laptop has more, you may raise `n_jobs`, but keep per-subject raw loading.

**The repo is public.** Never commit anything under `data/` or `results/` (already in `.gitignore`), and never
write the ADABase password anywhere. The user exports it in their own shell: `export ADABASE_PASSWORD=...`.
Commit messages: no Claude co-author / attribution lines.

## 2. Data

Neither the raw data nor the features are in git.

**Raw HDF5 (needed).** The first laptop deleted the raw files after feature extraction. The feature parquets only
store `win_start` *within* each segment, so `t_session_s`, the per-subject block order (audit Q2), the event logs
(Q13) and the k-drive baselines (Q12) all need the raw files. Download (about 0.9 GB per subject, 27 GB in total;
2–12 min per subject):
```sh
.venv/bin/python src/load_adabase.py --subject 0     # downloads one subject and prints its segments
```
Keep the raw files if disk allows; E3 and E6 need them again. With little disk, process one subject at a time and
store what you need (segment absolute start times, event logs) before deleting.

**Features and old results (optional; saves hours of retraining).** The user can copy these from the first laptop
(they're not on GitHub). On the first laptop, run:
```sh
cd reasoning_model && tar czf review_input.tar.gz data/features results/*.parquet results/*.csv \
    results/evidence results/evidence_fusion results/explanations results/explanations_fusion \
    results/explanations_*_holdout.jsonl results/models
```
Unpack it into `reasoning_model/` here. Without it, rebuild with `python src/features.py --all` (keeps raw unless
`--delete-raw`), then `python src/train.py --task binary --tune` and `python src/fusion.py` (several hours on CPU).
Note: the old `results/handoff.tar.gz` does **not** contain the `oof_*.parquet` files that E1/E2/E4 read.

## 3. Code change needed before Step 0

`features.extract` ([src/features.py](src/features.py), the `rows.append` around line 193) must also store the
segment's absolute start time, so `t_session_s` can be built. The timestamp is the HDF5 `index` field, in ms, which
`Subject.read` already reads ([src/load_adabase.py:83](src/load_adabase.py#L83)). Alternatively, write a separate
`src/review/segments.py` that only calls `Subject(sid).segments()` plus `t.read(start, start+1, field="index")` per
segment and saves `results/review/segments.parquet` (subject, study, phase, level, t0_ms, dur_s). That avoids touching
existing code. The task brief requires showing the user the diff before changing any existing `src/*.py`.

## 4. Audit answers already found (verify, then copy into `results/review/AUDIT.md`)

| Q | Answer | Source |
|---|---|---|
| 1 | Yes, both. low = 1-back single **and** 1-back dual. Counts (dual, n): (0,1) 189, (0,2) 190, (0,3) 188, (1,1) 192, (1,2) 191, (1,3) 188. P(high) = 0.665. | `train.py:61-67`, `features.py:192-194` |
| 2 | **Open: needs raw timestamps.** The code assumes levels 1–6 = 1/2/3-back single then dual, but nothing verifies the order per subject. | `load_adabase.py:7` |
| 3 | Not dropped windows: n-back blocks are shorter than 120 s. Last `win_start` = 75 s (6 windows) or 90 s (7 windows), so blocks are ≈105–120 s long. 6 vs 7 varies per subject × level. k-drive segments are ≥ 300 s, so always 19 windows. Print the exact segment durations from raw. | `features.py:190` |
| 4 | **21/30** subjects have AU data. No AU: 0001-AGDJ, 0010-ISJP, 0011-KISN, 0015-LINI, 0019-PFAC, 0023-SFKF, 0024-SZLE, 0025-TBMO, 0029-ZZOV. The AU agent's 0.880 comes from only those 21 subjects (799 windows); fusion and main use all 30. 0006-BRJG has **no eye data** either. | `fusion.py:165-167` |
| 5 | Excluded-s fold model: no subject leakage. Each fold predicts k-drive for its own held-out subject only. | `train.py:164,175-178`; `fusion.py:134,139-143` |
| 6 | Yes. Optuna, tree count (median early-stopping iteration over 5 inner folds) and isotonic (on inner OOF) use only outer-training subjects. The final model is refit on all of them with that tree count. Caveat: inner models train **with** modality dropout, so the isotonic map is fitted on dropout-trained models but applied to the final model. | `train.py:139-149`, `104-121` |
| 7 | Confirmed: SD over **all** windows of that subject × study (baselines + all six levels), including the test subject's own windows (label-free but transductive; a kiosk can't do this). Centre = baseline 2, or baseline 1 when baseline 2 is missing. | `features.py:213-219` |
| 8 | Includes the verifier's error message. Rejected output + "Rejected by the verifier: …" are appended, then one retry. | `reasoner.py:234-239` |
| 9 | **Not the same configuration.** The LoRA comparison runs base and LoRA through the MLX server, which has **no JSON-schema constraint**. The main evaluation used Ollama **with** the schema. Without the schema the 3B model drops keys and writes numbers as strings (`reasoner.py:107-108`), hence 0.90 vs 0.077. The LoRA targets also include template outputs for windows where the LLM failed. | `reasoner.py:119-127`, `finetune.py:41-48, 92-100` |
| 10 | **Open:** check `data/adabase/Documentation.pdf` (sensor placement). | |
| 11 | 0–20: unweighted mean of six subscales; observed range 0–18.7. | `load_adabase.py:87-91` |
| 12 | **Open (raw).** Features contain n-back baselines 1 (5 min) and 2 (≈105 s) and k-drive baseline 1 only. `KEEP` asks for k-drive baseline 2 but none was found in any subject. List all segments from raw to confirm. | `load_adabase.py:30`, `features.py:216` |
| 13 | **Open (raw/docs):** check the HDF5 tables (`PERFORMANCE`, others) for stimulus onsets. | |

## 5. What to do

Follow `CLAUDE_CODE_REVIEW_TASKS.md` exactly: Step 0 (finish the audit, build `windows.parquet` and `oof.parquet`)
→ E1, E2, E4 → **stop and report to the user**. All new code goes in `src/review/`, all outputs in `results/review/`.
