# rPPG benchmark: rppg1 PhysFormer vs rPPG-Toolbox (Liu et al., NeurIPS 2023)

Video-level HR (FFT over the whole video), toolbox protocol (bench/run.py). Published = rPPG-Toolbox Table 7. ± = standard error.

| Method | Train | Test | n videos | MAE ↓ | RMSE ↓ | MAPE % ↓ | Pearson ↑ | SNR dB ↑ | within 5 bpm | Published MAE / RMSE / MAPE / r / SNR |
|---|---|---|---|---|---|---|---|---|---|---|
| CHROM | - | MCD-rPPG | 200 | 16.09 ± 0.98 | 21.19 ± 47.13 | 18.05 ± 0.95 | 0.22 | -5.97 ± 0.21 | 28% | — |
| CHROM | - | UBFC-rPPG | 42 | 8.38 ± 3.10 | 21.78 ± 226.69 | 7.37 ± 2.54 | 0.44 | -2.27 ± 0.66 | 81% | 4.06 / 8.83 / 3.84 / 0.89 / -2.96 |
| CVPR Lab phase1_physformer | MCD-rPPG | MCD-rPPG | 40 | 2.50 ± 1.00 | 6.82 ± 29.14 | 3.13 ± 1.24 | 0.85 | -0.88 ± 0.50 | 88% | — |
| CVPR Lab phase1_physformer | MCD-rPPG | UBFC-rPPG | 42 | 2.99 ± 0.91 | 6.63 ± 23.59 | 2.96 ± 0.84 | 0.93 | -1.25 ± 0.58 | 81% | — |
| CVPR Lab phase1_physformer | MCD-rPPG | UBFC-rPPG | 42 | 24.63 ± 2.89 | 30.94 ± 179.72 | 22.99 ± 2.41 | 0.11 | -8.29 ± 0.39 | 26% | — |
| CVPR Lab phase1_physformer | MCD-rPPG | MCD-rPPG | 40 | 14.99 ± 2.27 | 20.74 ± 101.61 | 17.54 ± 2.57 | -0.13 | -5.78 ± 0.27 | 32% | — |
| CVPR Lab phase2_physics,stem_tdc=False | MCD-rPPG | MCD-rPPG | 40 | 3.49 ± 1.59 | 10.65 ± 92.63 | 3.68 ± 1.43 | 0.52 | -1.15 ± 0.48 | 88% | — |
| CVPR Lab phase2_physics | MCD-rPPG | UBFC-rPPG | 42 | 6.26 ± 1.77 | 13.08 ± 66.58 | 5.60 ± 1.49 | 0.74 | -1.92 ± 0.56 | 69% | — |
| CVPR Lab phase2_physics | MCD-rPPG | UBFC-rPPG | 42 | 22.43 ± 2.19 | 26.54 ± 116.63 | 21.58 ± 1.98 | -0.27 | -8.24 ± 0.44 | 12% | — |
| CVPR Lab phase2_physics,eta=1.0 | MCD-rPPG | MCD-rPPG | 40 | 10.88 ± 1.65 | 15.09 ± 58.29 | 12.77 ± 1.83 | 0.19 | -5.02 ± 0.40 | 38% | — |
| CVPR Lab phase2_physics | MCD-rPPG | MCD-rPPG | 40 | 11.13 ± 1.83 | 16.06 ± 84.67 | 12.69 ± 1.88 | -0.04 | -5.24 ± 0.41 | 42% | — |
| CVPR Lab phase3_dualstream | MCD-rPPG | MCD-rPPG | 40 | 3.60 ± 1.17 | 8.22 ± 40.39 | 4.02 ± 1.13 | 0.68 | -1.01 ± 0.51 | 82% | — |
| CVPR Lab phase3_dualstream | MCD-rPPG | UBFC-rPPG | 42 | 3.54 ± 1.32 | 9.26 ± 59.70 | 3.24 ± 1.07 | 0.86 | -1.19 ± 0.59 | 81% | — |
| CVPR Lab phase4_frequency | MCD-rPPG | MCD-rPPG | 40 | 5.04 ± 1.38 | 10.10 ± 45.03 | 5.75 ± 1.48 | 0.56 | -1.20 ± 0.46 | 78% | — |
| CVPR Lab phase4_frequency | MCD-rPPG | UBFC-rPPG | 42 | 2.64 ± 0.62 | 4.79 ± 9.40 | 2.69 ± 0.62 | 0.97 | -0.69 ± 0.53 | 81% | — |
| PhysFormer (rppg1) | MCD-rPPG | MCD-rPPG | 40 | 2.04 ± 1.27 | 8.28 ± 65.33 | 2.02 ± 1.08 | 0.66 | 1.02 ± 0.51 | 95% | — |
| PhysFormer (rppg1) | MCD-rPPG | UBFC-rPPG | 42 | 5.36 ± 1.61 | 11.72 ± 74.95 | 6.28 ± 2.47 | 0.74 | -1.00 ± 0.56 | 76% | — |
| POS | - | MCD-rPPG | 200 | 15.56 ± 0.95 | 20.59 ± 41.48 | 17.39 ± 0.94 | 0.28 | -6.10 ± 0.21 | 32% | — |
| POS | - | UBFC-rPPG | 42 | 4.22 ± 1.67 | 11.64 ± 86.02 | 4.23 ± 1.58 | 0.84 | -1.49 ± 0.56 | 81% | 4.08 / 7.72 / 3.93 / 0.92 / -2.39 |

Published rows without our counterpart yet:

- PhysFormer trained on PURE, tested on UBFC-rPPG: MAE 1.44, RMSE 3.77, MAPE 1.66, r 0.98
- PhysFormer trained on UBFC-rPPG, tested on PURE: MAE 12.92, RMSE 24.36, MAPE 23.92, r 0.47
- PhysFormer trained on SCAMPS, tested on UBFC-rPPG: MAE 4.56, RMSE 10.48, MAPE 5.18, r 0.81
- POS trained on -, tested on PURE: MAE 3.67, RMSE 11.82, MAPE 7.25, r 0.88
- CHROM trained on -, tested on PURE: MAE 5.77, RMSE 14.93, MAPE 11.52, r 0.81

Deviations from the toolbox: rppg1's PhysFormer stem is 96 channels wide in all three conv layers (official: 24 / 48 / 96) and has no dropout; frequency losses from the toolbox (bench/toolbox_loss.py; rppg1/losses.py uses un-normalised power); fp16 mixed precision; batch 4 = 1 clip x 4 accumulated steps (6 GB GPU); validation split by subject.