# Brief for Claude Code: validity diagnostics and fixes for the ADABase cognitive-load pilot

You are working on an existing pipeline that estimates cognitive load from physiology on ADABase.
It uses LightGBM per-modality agents, fusion by logistic regression, SHAP explanations, and a Qwen2.5-3B
reasoner with a verifier. An external review found that several headline results may be artefacts of the
study design, not evidence of cognitive load. Your job is to run the diagnostics below **in order**, save
every result, and write a summary report. **Do not change the main model's design until the diagnostics are done.**

## 0. Ground rules

- Machine: MacBook, 8 GB RAM, 8 CPU cores, no CUDA (Apple Silicon/MLX available). Everything must run on CPU.
  Use `n_jobs<=6`. Never load all raw 1 ms signals for all subjects at once; work per subject.
- **Never modify raw data** (`data/adabase/`) or existing result files. Write everything new under `results/review/`
  and new code under `src/review/`. One script per experiment: `src/review/e01_order.py`, etc.
- Seed everything (`seed=0..4` where seeds are needed) and report the seed SD.
- **The subject is the unit of analysis.** Never use window-level significance tests (DeLong, McNemar on windows,
  window-level bootstrap). Windows overlap and are nested in subjects.
- Every experiment writes: (1) a CSV of numbers, (2) one PNG figure (matplotlib, `fig.savefig`), and
  (3) a short entry in `results/review/REPORT.md` with hypothesis → result → verdict (using the decision rule given).
- If an assumption in section 1 turns out false, note it in the report and adapt; don't silently skip the step.
- Show me the diff before you modify any existing `src/*.py` file.

## 1. Step 0: audit and build two shared tables (do this first)

First find the existing pipeline code and outputs; ask me if you can't. Then build these two tables, which every later experiment reads.

**`results/review/windows.parquet`**: one row per window, both tasks. Columns:
`subject, task ('nback'|'kdrive'), block_index (0..5 for n-back in session order; 0..2 k-drive), level (1..3),
dual (0/1; n-back only), win_in_block (0..6 for n-back, 0..18 for k-drive), t_session_s (window start time since
session start, seconds), label (0 low / 1 high), tlx (NASA-TLX of that level), has_face (0/1)`, plus all 40
features as **raw** values (`raw_<feat>`) **and** as used by the model (`z_<feat>`), plus `q_<modality>` quality
and `avail_<modality>` flags.

**`results/review/oof.parquet`**: out-of-fold predictions already produced by the LOSO runs. Columns: `subject, task,
block_index, win_in_block, model ('main_cal','main_uncal','fusion','agent_AU','agent_eye',…, one per ablation),
p_high, logit_<agent> (fusion inputs), contrib_<agent>`.
If OOF predictions were not saved, re-run the existing LOSO training once with saving enabled. Change nothing else.

**Answer these audit questions in `results/review/AUDIT.md`.** Cite file and line for each.
1. Does the n-back set include both single- and dual-task blocks? Is "low" = 1-back single + 1-back dual?
   Print class counts per (dual, level). Expected prior P(high) ≈ 0.667.
2. What is the actual block order in the session for n-back and for k-drive? Is it fixed for every subject?
   Print the order per subject from timestamps.
3. Why are there 1138 n-back windows (max 30×6×7 = 1260) but exactly 1710 k-drive windows (30×3×19)?
   Tabulate the dropped windows by subject × block × reason.
4. How many subjects have face/AU data? Was the AU agent's AUROC (0.880) computed on only those subjects while
   other agents/fusion used all 30?
5. Are k-drive predictions for subject s produced by the LOSO fold model that **excluded s**? Or by one model
   trained on all 30 subjects' n-back data (which would be subject leakage)?
6. Are Optuna, tree count (early stopping) and isotonic calibration all fitted only on outer-training subjects?
   Is the final fold model refit on all outer-training subjects with the chosen tree count?
7. How is each subject's z-score scale computed? Confirm it is the SD over all windows of that task, including
   the test subject's own windows.
8. What does the reasoner's "retry once" send? The identical prompt at temperature 0, or a prompt that includes
   the verifier's error message?
9. For the LoRA comparison (5 held-out subjects, 50 windows): is the base model run with the **same** prompt,
   JSON schema and decoding as in the main 300-window evaluation? Base first-try failure was 0.90 there but
   0.077 in the main evaluation; explain the difference.
10. Where are the PPG and skin-temperature sensors placed (finger / earlobe / wrist)? Check the ADABase docs.
11. What scale is NASA-TLX on (0–20 or 0–100)?
12. Does ADABase contain a no-task driving baseline for k-drive (a k-drive "baseline 2/3")? List the available
    baseline segments per task.
13. Does ADABase include stimulus/event logs (n-back stimulus onsets, consonant onsets in dual task)?

## 2. Shared evaluation utilities (`src/review/stats_utils.py`)

Implement these once and reuse them everywhere:
- `per_subject_auroc(df, score, label)` returns a per-subject AUROC series (skip subjects lacking both classes;
  report how many were skipped).
- `subject_bootstrap_ci(values, B=2000, seed=0)` gives the mean and 95% percentile CI over subjects.
- `pooled_auroc_cluster_ci(df, B=2000)` gives the pooled AUROC with a CI from resampling **subjects** with replacement.
- `paired_subject_diff(a, b)` gives the per-subject difference of two models: mean, bootstrap CI, Wilcoxon p.
  Apply Holm correction across the comparisons within each experiment.
- `block_permutation_pvalue(...)` shuffles which **blocks** are high/low within each subject (keep the
  per-subject count of high blocks fixed). Retrain with **fixed** hyperparameters (no Optuna), 200 permutations.
- `ece(p, y, n_bins=10)`, Brier score and a reliability-diagram plot.
- Threshold: choose it on inner-CV OOF predictions (maximise balanced accuracy), never on the test subject.

## 3. Experiments (run in this order; cheapest and most diagnostic first)

### E1: order / time-on-task confound (most important)
*Hypothesis:* because block order is fixed (low is always first in each triplet; dual = second half of the session),
the model partly tracks time or block position rather than load. Theory: time-since-session-start alone gives
AUROC 0.75 on these labels; position within the triplet gives 1.00.
1. Order-only model: LOSO logistic regression on `[t_session_s, block_index]` only. Report per-subject and
   pooled AUROC with CIs. Report this baseline next to every n-back result from now on.
2. **Sawtooth test.** For each subject, compute the mean OOF `p_high` (main_cal and fusion) per block (6 values).
   Plot all subjects (thin lines) plus the mean (thick), with x = block in session order. Paired Wilcoxon
   across subjects: block 2 (3-back single) vs block 3 (1-back dual). Also run a sign test.
3. Repeat the sawtooth on **raw** block-mean features: pupil, HR, RMSSD, EDA tonic, PPG amplitude, SKT mean,
   SKT slope, AU23, AU25, AU26, AU4.
4. Within-block drift: per subject, regress `p_high` on `win_in_block` inside each constant-load block; report the
   mean slope with CI.
5. Mixed models on block means (statsmodels MixedLM): `y ~ n_level + block_index + (1|subject)` for `logit(p_high)`
   and for each raw feature above. Note: `dual` is identical to "second half of session", so it cannot be separated
   from time. Say so in the report.

*Decision rule:* the signal counts as **load-related** only if P(block 2) > P(block 3) in ≥ 24/30 subjects
(sign test p < 0.001) **and** n_level stays significant with block_index in the model. If P(block 3) ≥ P(block 2),
write "the model largely tracks time/order" in the report.
Output: `e01_order.csv`, `e01_sawtooth.png`.

### E2: compare all modalities on the same subjects
Recompute every agent, every ablation, the main model and fusion on **only the subjects with face data**, then
fusion on the subjects without face data. Report paired per-subject differences (AU vs eye, AU vs fusion,
contactless vs contact) with CIs.
*Decision rule:* "AU is the best modality" holds only if AU beats eye and fusion on identical subjects with a
paired CI excluding 0.
Output: `e02_common_subset.csv`, a forest plot `e02_forest.png`.

### E3: what the AU signal is (articulation vs effort)
1. Split the 20 AUs into **upper face** (AU1, 2, 4, 5, 6, 7, 9, 43/45 if present) and **lower face**
   (AU10, 12, 14, 15, 17, 20, 23, 24, 25, 26, 28 if present). Print the exact list used.
2. Train AU-upper-only and AU-lower-only agents (same LOSO protocol). Evaluate them on single-task and dual-task
   triplets separately, plus k-drive transfer for each.
3. Train on single-task blocks only and test on single-task blocks. Single-task n-back is visuospatial, so
   verbal rehearsal is not expected there.
4. Face-detection rate and AU-detector confidence (if available) per level. If event logs exist (audit Q13),
   compute AU25/AU26 time-locked to consonant onsets in dual blocks (−1 to +3 s), averaged per subject.

*Interpretation:* lower-face ≫ upper-face, concentrated in dual blocks, inverting on k-drive → **articulation /
task behaviour**. Upper-face carrying the signal in single **and** dual blocks without inverting → facial-effort
evidence.
Output: `e03_au.csv`, `e03_au.png`.

### E4: do availability and quality leak the label?
1. LOSO logistic regression on `avail_*` + `q_*` only → per-subject AUROC.
2. Refit fusion with the availability weights v_m fixed to 0; compare AUROC.
3. Mean availability and quality per level, per modality.

*Decision rule:* leak if flags-only AUROC CI excludes 0.5 or fusion AUROC drops by more than 0.01 without v_m.
Output: `e04_leak.csv`.

### E5: why k-drive collapses (baseline mismatch vs task specificity)
Currently n-back is centred on baseline 2 (stimulus-matched) but k-drive is centred on baseline 1 (black screen).
1. On the existing k-drive predictions: mean `p_high` vs the base rate 0.667; reliability diagram; per-subject
   vs pooled AUROC.
2. **Symmetric centring A:** retrain with **both** tasks centred on baseline 1.
3. **Symmetric centring B:** centre each subject × task on that subject's own median over all windows of the task
   (label-free; an upper bound for any re-baselining).
4. If a stimulus-matched k-drive baseline exists (audit Q12), use it as variant C.
5. Ceiling: LOSO within k-drive. Reverse direction: train on k-drive, test on n-back. Both strictly LOSO, so
   the test subject is never in training for either task.
6. Manipulation check: per-subject TLX difference (level 1 vs 2–3) in k-drive vs n-back.

*Interpretation:* pooled ≪ per-subject AUROC → offset problem. Symmetric centring recovers it → baseline
mismatch. High within-k-drive ceiling but low transfer → task specificity. Low ceiling or small TLX difference
→ weak k-drive manipulation.
Output: `e05_kdrive.csv`, `e05_reliability.png`.

### E6: why the contact-physiology agents are at chance
1. **Positive control:** baseline 2 vs any task block, using the HR, EDA, RSP, PPG and SKT agents (LOSO).
   Expect AUROC > 0.8. If HR fails, suspect a feature bug or over-aggressive masking.
2. Per-window HR from ECG vs HR from PPG: correlation and MAE per subject. Expect r > 0.95.
   PTT range check (~150–350 ms). Fraction of windows masked per modality × level.
   SCR-count distribution: is it mostly zeros?
3. Univariate per-subject effect sizes (dz with 95% CI) on **raw block-level** features (120 s): 1-back vs
   3-back, and single vs dual (the latter confounded with time; label it so).
4. Window-length sweep: 30 s, 60 s, 120 s (one window per block) for each contact agent.
5. TLX relabelling: high/low = within-subject TLX above/below the subject's median; retrain the contact agents.

*Decision rule:* the positive control passes, block-level |dz| < 0.3, and longer windows don't help → report as a
**real small effect for this contrast**, not a pipeline failure.
Output: `e06_physio.csv`, `e06_effects.png`.

### E7: PPG amplitude ↑ and SKT slope ↑ (directions opposite to the literature)
1. Plot raw SKT and raw PPG amplitude against `t_session_s` for every subject (one small panel each, blocks shaded).
2. Mixed model: `feat ~ t_session_s + n_level + (1|subject)`.
3. Per-subject sign test of the **raw** high−low difference.

*Interpretation:* a monotone trend over the session, with n_level non-significant once time is in the model,
means a warming/acclimatisation drift aliased onto "high" by the fixed order. Finger PPG amplitude and finger
skin temperature should fall under stress; if the sensors are not on the finger, note that.
Output: `e07_drift.csv`, `e07_drift.png`.

### E8: kiosk-compatible normalisation
The current scale uses each subject's SD over the whole task, which a kiosk will never have. Retrain with:
(i) baseline-only centring and scaling; (ii) baseline centring with the pooled SD from training subjects;
(iii) centring on only the 60–120 s before the first block. Report AUROC for each.
Output: `e08_norm.csv`.

### E9: final statistics for the main results
For the main model, fusion and every ablation, all on a common subject set, report:
- per-subject AUROC mean [95% CI], median, IQR, and the number of subjects > 0.5;
- pooled AUROC with cluster CI;
- balanced accuracy / macro-F1 at the inner-CV threshold;
- Brier, ECE [CI] and a reliability diagram;
- block-permutation p-value (200 permutations, fixed hyperparameters);
- seed SD over seeds 0–4;
- the order-only baseline from E1 next to every row.

Note in the report: a significant permutation p-value only means "better than chance". The permutation also
destroys the order confound, so it does **not** show that the model measures load.
Output: `e09_main_table.csv`.

### E10: attribution-faithfulness upgrade
1. For each window, remove the top-3 SHAP features with three operators: (a) NaN (current), (b) set z = 0
   (baseline value), (c) replace with a value sampled from training subjects.
   Measure Δ P(predicted class) for each.
2. Comparison sets: SHAP top-3; **global** top-3 importance (same for every window); SHAP ranks 4–6; random 3.
   If instance SHAP ≈ global top-3, the explanations add no per-window information. Say so.
3. Comprehensiveness and sufficiency curves (AOPC) for k = 1…10.
4. Sign test: removing positive-SHAP features should lower P(high), and removing negative ones should raise it.
   Report the % of windows that behave as expected.
5. ROAR: retrain LOSO without the global top-k features (k = 1, 3, 5) and report the AUROC drop.
6. Sanity check: train on within-subject shuffled labels; SHAP rankings should change.
   Report the rank correlation with the real model.
7. **Fusion:**
   - Recompute contributions against the training means: `c_m = w_m*(logit_m - mean_logit_m) + v_m*(avail_m - mean_avail_m)`.
   - Report the evidence part and the availability part separately.
   - Redo "remove the top agent" as evidence-only removal: set the logit to its training mean and keep avail
     unchanged.
   - Compare against the **2nd-ranked** agent, not a random one.
   - Note in the report that fusion faithfulness is near-tautological because the fusion is linear.

Output: `e10_faithfulness.csv`, `e10_aopc.png`.

### E11: reasoner fixes (before any hierarchical redesign)
1. **Failure taxonomy** on the existing 300-window run (single and fusion records). Classify every verifier
   failure: number not in record / rounding mismatch / wrong label / wrong confidence / unknown feature name /
   schema error / wrong direction word. Make a table.
2. Implement these fixes as a new reasoner variant. Keep the old one runnable for comparison.
   - `conclusion` and `confidence` are filled **by code** from the predictor, never generated by the LLM.
   - `evidence[]` items are enum-constrained IDs from the record, e.g. `{"id": "E3", "direction": "toward_high"}`.
     Code renders the numbers into the text. The LLM never types a number.
   - On verifier failure, retry **with the verifier's error message included** in the prompt.
   - Add semantic checks to the verifier: the stated top agent equals argmax |c_m|; every stated direction
     matches the sign of its contribution; every opposing agent with |c_m| > 0.2 appears in `conflicts[]`.
3. Re-run on 600 windows: 20 per subject × 30 subjects, sampled with a fixed seed. Prompts must be frozen on
   **separate development windows** that are not in this set.
   Report with subject-cluster bootstrap CIs:
   - first-try failure, final failure, abstain rate;
   - top-1 agent agreement, Kendall τ (cited order vs |c_m| order), sign agreement;
   - coverage = Σ_cited |c| / Σ_all |c|, conflict recall, sufficiency (the cited contributions alone give the same label);
   - latency p50/p95 on this Mac.
4. **Counterfactual and invariance tests:**
   - Swap the AU and eye contributions in the record (with a consistent label). The stated driver should change.
   - Reorder JSON keys or rename the window ID. The text should not change materially.

Output: `e11_reasoner.csv`, `e11_failures.csv`.

### E12: hierarchical explainer (only if E11 leaves fusion first-try failure > 5%)
Design (already specified):
- Gate to available agents with quality ≥ 0.5, top-2 by |evidence contribution|.
- One specialist call per gated agent, then a director call.
- Same Qwen2.5-3B; verifier and retry rules as in E11.

Run a paired comparison on the same 600 windows. Arms:
1. Flat, no role.
2. Flat, role prompt.
3. Flat, **length-matched neutral prompt** (same token count and structure, no persona).
4. Hierarchical, no role.
5. Hierarchical, role prompt.

Measure the director's prompt length compared with the flat prompt.

**Adoption rule** (compare against the best flat arm *after* E11, not the old flat arm). Adopt hierarchical only if all hold:
1. The 95% subject-cluster bootstrap CI upper bound of the first-try-failure difference is < 0.
2. The CI upper bound of the abstain increase is < 3 points.
3. The CI lower bounds of the top-agent agreement and conflict-recall differences are > −3 points.
4. p95 end-to-end latency is ≤ the kiosk budget (ask me for it).

Otherwise drop it.
Output: `e12_hier.csv`.

### E13: LoRA re-evaluation (after E11)
- Subject-wise 5-fold over all 30 subjects. Train only on first-try-verified outputs from training subjects.
- Compare with the **same** base configuration (prompt, schema and decoding identical).
- Report the E11 metrics, plus distinct-1/2 and self-BLEU across windows, n-gram overlap with the training
  outputs, and the counterfactual/invariance tests.
- Also compare against a deterministic **template** explanation. If LoRA is not better than the template on
  semantic accuracy (top-agent, sign, conflict recall), say so.

Output: `e13_lora.csv`.

## 4. Report (`results/review/REPORT.md`)

For each experiment, give one paragraph: hypothesis, numbers with CIs, the figure, and the verdict according to
its decision rule. End with these four sections:
1. **Claims we can make**, each with its evidence.
2. **Claims we cannot make yet.** Defaults, unless experiments overturn them:
   - that the model measures cognitive load rather than block order/time;
   - that facial AUs are a load biomarker;
   - that contactless beats contact physiology;
   - that the model generalises across tasks;
   - that contact physiology carries no load information;
   - that PPG/SKT directions reflect load;
   - that explanations are faithful beyond the model's own value function;
   - that LoRA eliminates hallucination;
   - any "comparable to / below the state of the art" comparison with the ADABase paper (0.88 AUC; different
     protocol: 51 subjects, 2-min windows, likely non-subject-wise 10-fold CV).
3. **Updated main results table** (from E9).
4. **Recommended next step.**

## 5. Run order and time budget

Step 0 audit (½ day) → E1, E2, E4 (≈1 h total) → E3, E5, E7 (≈ ½ day) → E6, E8, E9 (≈ ½ day)
→ E10 (≈ ½ day) → E11 (≈ 1 day incl. ~600-window LLM run overnight) → E12/E13 only if their gates are met.

**Stop and report to me after Step 0 + E1 + E2 + E4.** Those results decide whether the rest is worth running as planned.

## 6. Context for later (no action now)

The final kiosk model will be trained on our own recordings: rPPG, thermal, ECG and EEG, about 30 participants.
The planned protocol: counterbalanced (Williams Latin square) 0/1/2/3-back visuospatial n-back, 3-min blocks,
60 s rest before each block, a silent timed-arithmetic stress block last, and RTLX + Paas ratings after each
block. Normalisation will use only baselines a kiosk can record. Design all new code so it doesn't assume
ADABase-specific modalities, and keep normalisation kiosk-compatible.
