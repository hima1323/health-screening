I want a rigorous scientific review of an explainable multimodal model for cognitive-load estimation from physiological signals, followed by a prioritised plan to improve it. Act as a reviewer with expertise in psychophysiology, affective computing and ML evaluation methodology. Be critical. Tell me where the results might be artefacts, confounds or leakage. Don't just tell me they look reasonable.

## 1. Context and end goal

This is a university HCI project (IIT, semester 5, two students). The end product is a contactless health-screening kiosk. The final model has to estimate cognitive load / stress from **rPPG (camera pulse), thermal imaging, ECG and EEG recorded together on the same people**. No public dataset has all four, so the final model will be trained only on our own recordings, which will be small: expect roughly 15–30 participants. Public datasets are only for building and debugging the pipeline and for pretraining or validating single modalities. We never pool samples from different datasets as if they came from the same person.

Design principle: **the predictor decides, the reasoner explains.** A calibrated tree model produces the label and probability. A small LLM only writes an evidence-cited explanation. It can never change the label, and a verifier rejects any number that isn't in the evidence record.

Hardware: MacBook, 8 GB RAM, 8 CPU cores, no CUDA GPU (Apple Silicon/MLX is available). Any suggestion has to be feasible on this machine.

## 2. Current stage: pilot on ADABase

Dataset: ADABase (Oppelt et al., Sensors 2023, doi 10.3390/s23010340). Public release: **30 subjects** (the paper reports 51). Signals are on a 1 ms grid: ECG, PPG, EDA, RSP, EMG, skin temperature (SKT), eye tracker (250 Hz) and face Action Units (~25 Hz, 20 AU probabilities). There is **no raw video, so no rPPG**, and no EEG or thermal. About 30% of subjects have no face/AU data.

Tasks: n-back levels 1–6 (1/2/3-back single task, then 1/2/3-back dual task, 120 s each). k-drive levels 1–3 (300 s each). Baseline 1 is a 5-minute black screen. Baseline 2 shows the same stimulus with no task. NASA-TLX is collected per level.

### Pipeline
1. **Windows:** 30 s, 50% overlap, within each run.
2. **Labels:** binary low = 1-back, high = 2/3-back (main task). Also a 3-class 1/2/3-back task, and raw NASA-TLX as a regression target. **k-drive is held out entirely** as a cross-task test (level 1 = low, levels 2–3 = high).
3. **Features (40):** ECG HR/RMSSD/SDNN/pNN50 (no LF/HF because 30 s is too short). PPG rate/amplitude/PTT. EDA tonic/SCR count/amplitude. RSP rate/depth/variability. EMG RMS. SKT mean/slope. Pupil mean/slope, blink rate, fixation duration. 20 AU activation rates. Features come from NeuroKit2.
4. **Normalisation:** per-subject z-scores. Centred on baseline 2 (same stimulus, no task) and scaled by the subject's SD over all windows of that task. Centring on the black-screen baseline 1 gave pupil z ≈ +5 (a luminance effect) and |z| > 10 for EMG and rare AUs (p95 |z| 10.0 vs 2.6 with stimulus-matched centring). k-drive has no extracted baseline 2, so **k-drive is centred on baseline 1**.
5. **Quality:** a signal-quality index per modality per window. A modality is masked when its quality is below 0.5.
6. **Predictor:** LightGBM (num_leaves 15, lr 0.03, ≤500 trees, min_child_samples 20, feature_fraction 0.7, balanced classes, 30% modality dropout). Leave-one-subject-out (LOSO). Inside each fold, a 5-fold subject-wise inner CV sets the tree count, provides the Optuna objective (25 trials) and produces out-of-fold probabilities for isotonic calibration. Explanations come from SHAP.
7. **Modality agents + fusion:** one LightGBM per modality (calibrated P(high), SHAP over its own features, marked unavailable when missing or low quality). Agents are fused by logistic regression with non-negative weights, trained on inner out-of-fold agent outputs. The inputs are each agent's logit (0 when unavailable) and an availability flag. The log-odds split exactly into per-agent contributions: contribution_m = w_m·logit(p_m) + v_m·avail_m. The logit weights w_m are ≥ 0, while the availability weights v_m and the intercept are unconstrained.
8. **Evidence record per window:** label, calibrated probability, top-6 SHAP features with raw value and z-score, rule-based expected directions, quality.
9. **Reasoner:** Qwen2.5-3B-Instruct (Ollama, temperature 0, JSON-schema constrained output) produces `{conclusion, confidence, evidence[], conflicts[], abstain}`. A verifier checks the label, confidence, feature names and every number. On failure it regenerates once, then abstains. Abstention is decided by rule (confidence < 0.6, or all cited modalities low quality). A LoRA fine-tune (MLX) of the same LLM was trained on verified outputs.

## 3. Results (30 subjects, 1138 n-back windows, 1710 k-drive windows)

**Main predictor**
| Set | Bal. acc | Macro-F1 | AUROC | ECE |
|---|---|---|---|---|
| n-back LOSO (calibrated) | 0.715 | 0.727 | 0.801 | 0.033 |
| n-back LOSO (uncalibrated) | 0.736 | 0.735 | 0.808 | 0.068 |
| k-drive cross-task | 0.584 | 0.534 | 0.592 | 0.247 |
| 3-class n-back | 0.621 | 0.620 | – | – |
| NASA-TLX regression | MAE 3.26, Spearman 0.36 overall, 0.52 within-subject | | | |

Reference: the ADABase paper reports a fused n-back AUC of 0.88 / F1 0.77 (51 subjects, 2-minute windows, 10-fold CV, which is probably not subject-wise).

**Fusion of modality agents**
| Model | Bal. acc | AUROC | ECE |
|---|---|---|---|
| Fusion, n-back LOSO | 0.789 | 0.873 | 0.043 |
| Fusion, k-drive | 0.586 | 0.590 | 0.233 |
| AU agent (70% available) | 0.804 | 0.880 | 0.040 |
| Eye agent | 0.675 | 0.731 | 0.040 |
| SKT agent | 0.562 | 0.588 | – |
| ECG / PPG / EDA / RSP / EMG agents | ≈0.50 | 0.44–0.54 | – |

**Ablations (n-back AUROC / k-drive AUROC)**
- All features: 0.804 / 0.661
- Contactless (eye + AU): **0.847** / 0.601
- Contact physiology only (ECG, PPG, EDA, RSP, EMG, SKT): **0.622** / 0.642
- Only AU: 0.805 / **0.456**. All minus AU: 0.733 / **0.707**
- Only eye: 0.729 / 0.665. All minus eye: 0.741 / 0.550
- Each single contact modality: 0.45–0.61

**Learned directions vs literature** (mean z high−low, consistent across all 30 folds): pupil ↑, HR ↑, RMSSD ↓, pNN50 ↓ and PPG rate ↑ agree with the literature. **PPG amplitude ↑ (literature expects ↓, from vasoconstriction) and SKT slope ↑ (literature expects ↓) disagree.** The strongest AU effects are AU23 ↓, AU14 ↓, AU25 ↑ and AU26 ↑ (lip/jaw).

**Faithfulness:** removing the 3 cited features drops the probability by 0.294, against 0.024 for 3 random features. Cited > random in 96.5% of windows. For fusion (removing the top agent vs a random agent): 0.279 vs 0.036, 87.6%.

**Reasoner (300 windows, 30 subjects)**
| Record | First-try hallucination | Final unverified | Abstain | Citation acc. |
|---|---|---|---|---|
| Single model | 7.7% | 7.3% | 17% | 0.962 |
| Fusion | 17.0% | 15.3% | 24% | 0.9995 |

LoRA vs base (5 held-out subjects, 50 windows): first-try failure went from 0.90 to 0.00 (single) and from 0.10 to 0.00 (fusion).

## 3b. Proposed change to the reasoner (designed, not yet built)

The design is inspired by MAM (Zhou, Song & Shen, "MAM: Modular Multi-Agent Framework for Multi-Modal Medical Diagnosis via Role-Specialized Collaboration", Findings of ACL 2025). We take its role specialisation and specialist→director synthesis. We **drop** its LLM debate and voting, its LLM routing and its web retrieval, because in MAM the LLMs decide the label and in our system they must not.

```
LightGBM agents → fusion LR → label, confidence, per-agent contributions   (decides; unchanged)
   │
   ├─ gate: agent available, quality ≥ 0.5, top-2 by |w·logit p| (evidence part only, not the availability term)
   ├─ specialist call per gated agent (same Qwen-3B, role prompt, e.g. "psychophysiologist, AU signals")
   │    input: that agent's P(high), top features, z, quality → 1–2 sentences → verifier
   │    on failure: retry once, then drop that finding (the window is not abstained)
   ├─ director call: fusion record + verified specialist findings
   │    → {conclusion, confidence, evidence[], conflicts[], abstain} → verifier → retry once → abstain
   └─ kiosk timeout → template explanation (the label never waits for the LLM)
```

The motivation is that the 3B model fails verification more often on the large fusion record (17.0% first try) than on the smaller single-model record (7.7%), so smaller focused prompts may help. All specialist calls are skipped when the rule says abstain.

Planned evaluation:
- A paired 2×2 (flat / hierarchical × no role / role prompt) on the same 300 windows (10 per subject × 30 subjects).
- Metrics: first-try hallucination, final unverified, abstain, citation accuracy, top-agent faithfulness (does the director cite the agent with the largest |w·logit p|?), latency.
- A per-subject cluster bootstrap (2000 resamples) for the difference against flat / no role.
- Pre-registered adoption rule: the CI of the first-try-failure difference lies below 0 with point estimate ≤ 10%, abstain rises ≤ 3 points, top-agent faithfulness does not drop, and p95 latency fits the kiosk budget.

Then:
- **LoRA redo:** subject-wise 5-fold, trained only on first-try-verified outputs.
- **Human study:** 40 windows stratified by correct/wrong prediction and agreeing/conflicting agents; 3–5 raters score correctness against the record, usefulness, "which sensor drove it" and trust, paired flat vs hierarchical.

## 4. Questions I need answered

1. **Validity of the n-back result.** Is the AU signal measuring cognitive load or a confound? Possibilities include mouthing or sub-vocal rehearsal of digits (AU23/25/26 are lip/jaw), different on-screen content or response behaviour between 1-back and 2/3-back, or task order and time-on-task (levels always run in the same order, so does load covary with fatigue?). Propose concrete analyses I can run on the existing data to test each confound.
2. **Why does contact physiology fail?** ECG/PPG/EDA/RSP/EMG agents are at chance, even though the literature reports HRV and EDA effects for n-back. Is it the 30 s windows, the 120 s blocks being too short for tonic EDA and SKT to respond, z-scoring that removes the effect, the baseline choice, feature definitions, or a real null? How should I diagnose this?
3. **The direction disagreements** (PPG amplitude ↑, SKT slope ↑). Are they physiologically plausible, or do they point to a bug, a normalisation artefact or an order effect?
4. **Cross-task collapse.** n-back AUROC 0.80–0.87 falls to 0.59 on k-drive, with ECE ~0.24. How much of this comes from the baseline mismatch (k-drive centred on baseline 1) versus real task specificity? Removing AU improves k-drive. What does that imply? What is a fair cross-task protocol?
5. **Evaluation methodology.** Are LOSO + nested subject-wise inner CV + isotonic calibration correctly designed? Are there any leakage paths, for example through the z-scoring SD computed over all windows of the task (including test labels' windows), overlapping windows, or Optuna? Is calibration worth the 2-point drop in balanced accuracy? Which statistical tests and confidence intervals should I report (per-subject bootstrap? permutation test against chance?) given 30 subjects?
6. **Explainability evaluation.** Is my faithfulness test (remove cited features, compare to random) sound, given that removal means the masked/NaN path in LightGBM? What stronger tests exist (e.g. ROAR, sufficiency/comprehensiveness, counterfactuals)? Are the reasoner metrics meaningful? The LoRA comparison on 50 windows from 5 subjects looks underpowered, and LoRA trained on verified outputs may be overfitting the verifier's format. How should I evaluate that properly, including whether humans find the explanations useful and correct?
7. **Moving to our own data.** For rPPG + thermal + ECG + EEG with roughly 15–30 participants, I need a recommended protocol: tasks (n-back? arithmetic stress / TSST-like? both?), counterbalancing, block length, baselines, window length, ground truth (NASA-TLX, condition label, salivary cortisol not available), and the sample size or power needed to detect the effect. Also: which features and agents to pretrain on public single-modality data (UBFC-rPPG/PURE for rPPG, MAHNOB-HCI for EEG, thermal datasets), and how to avoid domain-shift traps.
8. **Positioning.** How should I honestly describe these results in a report, given the paper's 0.88 AUC used a different protocol?
9. **The hierarchical explainer (section 3b).**
   a. Is there evidence that splitting a task into smaller prompts reduces hallucination or unfaithfulness in small (≤7B) LLMs, or does error compound across stages? What do you expect for my 17% first-try failure on fusion records?
   b. Gating explains only the top-2 agents. Does leaving out weak or conflicting agents make the explanation unfaithful by omission? How should completeness be measured?
   c. Can verified text still be unfaithful (right numbers, wrong causal story, e.g. "pupil dilation drove the high label" when the AU agent dominated)? Which automated check catches this: an NLI model, rank agreement between the order of evidence and the order of |contribution|, or something else?
   d. Is a role prompt a real gain or a prompt-length confound? What control prompt should I use?
   e. Is a paired 2×2 on 300 windows from 30 subjects with a cluster bootstrap adequately powered to detect a drop from 17% to 10% first-try failure? If not, what n?
   f. Is my pre-registered adoption rule reasonable, or is there a better decision criterion?
   g. Is MAM's evidence for role specialisation and multi-agent synthesis (role prompting gains in its Table 1, an inverted-U over the number of roles in its Fig. 3, and cumulative ablations that never remove discussion alone) strong enough to justify this design? Or is our own experiment the only real evidence?
10. **Human evaluation of explanations.** Is the design in section 3b valid? Which agreement statistic should I use? How do I stop raters favouring fluent text over correct text (automation bias)? Should wrong-prediction windows be included to test whether explanations help users notice model errors? What is the minimum number of raters and items?
11. **LoRA.** How do I detect the LoRA learning the verifier's surface format rather than faithful explanation? For example: lexical diversity, or perturbed records where I swap feature values and check that the text changes accordingly.
12. **Fusion contributions.** With contribution_m = w_m·logit(p_m) + v_m·avail_m and unconstrained availability weights, is "contribution" a misleading quantity to cite to users? Is my fusion faithfulness result (removing the top agent drops the probability by 0.279) inflated because removal also switches off the availability term? What reference point should contributions be measured against?
13. **Deployment.** If the LLM times out, the kiosk shows a template explanation. Does mixing template and LLM explanations bias a user study? Should the template be the control arm?

## 5. Output I want

- **A. Verdict:** 5–8 bullets on what is solid, what is suspect and what is likely wrong.
- **B. Threats to validity:** a ranked table (confound/leakage/artefact, how likely, how to test it on existing data, expected outcome if it's real).
- **C. Concrete experiments:** an ordered list. For each, give the hypothesis, the exact analysis (feature/split/model change), the metric, and the result that would change my mind. Cheapest and most diagnostic first. Everything must run on an 8 GB CPU laptop.
- **D. Recommended reporting:** which numbers, CIs and tests to report, and which claims I am **not** allowed to make yet.
- **E. Data-collection protocol** for our own four-modality study.
- **F. References:** key papers for each claim (n-back physiology, AU/mouthing confounds, cross-task generalisation in cognitive-load detection, faithfulness metrics for feature attributions, LLM explanation verification, faithfulness vs plausibility of LLM explanations, multi-stage/multi-agent LLM pipelines and error compounding, human evaluation of XAI). Papers I already know of: Jacovi & Goldberg 2020 (faithfulness vs plausibility), DeYoung et al. 2020 (ERASER: comprehensiveness and sufficiency), Turpin et al. 2023 ("Language Models Don't Always Say What They Think"). Only cite papers you are confident exist. If you are unsure of the details, say so.
- **G. Architecture verdict:** keep, modify or drop the hierarchical explainer, with the experiment and threshold that should decide it.
- **H. Explanation-evaluation protocol:** automated metrics plus a human study, with sample sizes and the statistics to report.

Where you're making assumptions about my data or code, state them explicitly and tell me what to check.
