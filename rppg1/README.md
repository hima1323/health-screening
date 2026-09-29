# PhysFormer

PyTorch implementation of "PhysFormer: Facial Video-based Physiological
Measurement with Temporal Difference Transformer" (Yu et al., CVPR 2022).

## Structure

- `model/physformer.py` — architecture: conv stem, tube tokenizer, temporal
  difference transformer blocks (TD-MHSA + ST-FF), rPPG predictor head.
- `losses.py` — Negative Pearson loss, frequency cross-entropy loss, label
  distribution loss (Eq. 6), and the curriculum-guided dynamic combination
  (Eq. 7).
- `dataset.py` — dataset interface skeleton (adapt to VIPL-HR / MAHNOB-HCI /
  MMSE-HR / OBF preprocessing — expects per-clip `frames.npy`, `wave.npy`,
  `hr.npy`).
- `train.py` — training loop matching the paper's recipe (Adam, lr=1e-4,
  wd=5e-5, 25 epochs, batch size 4, 160x128x128 clips).
- `utils.py` — HR estimation from a predicted rPPG signal via PSD peak.

## Architecture

```
input   (1, 3, 160, 128, 128)     B, RGB, T frames, H, W
  ↓ Stem                          3× [Conv3d→BN→ReLU→MaxPool(1,2,2)]
stem    (1, 96, 160, 16, 16)      kernels (1,5,5),(3,3,3),(3,3,3) — spatial ÷8, T untouched
  ↓ TubeTokenizer                 Conv3d kernel=stride=(4,4,4)
tokens  (1, 96,  40,  4,  4)      640 tokens, D=96
  ↓ 12 × TD-Transformer block     shape-preserving
blocks  (1, 96,  40,  4,  4)
  ↓ PredictorHead                 spatial mean → interp to T → Conv1d ×2
out     (1, 160)                  7.70M params
```

Pooling in the stem is spatial-only — the rPPG signal *is* the time axis, so
T is never downsampled there.

**TD-Transformer block**

```
x = LayerNorm(x + TD_MHSA(x))
x = LayerNorm(x + ST_FF(x))
```

**TD-MHSA** (Eqs. 3–5)

```
Q = BN(TDC(x))    TDC: conv(x) − θ·(center × summed temporal-neighbour weights), θ=0.7
K = BN(TDC(x))
V = Conv3d 1×1×1
attn = softmax(QKᵀ / τ)·V,  τ=2.0   ← not √D_h; sharpens attention ~5×
out_proj: Linear
```

TDC feeds the Q/K path only, so tokens attend on how they *change over time*
rather than how they look. BN is correct inside TD-MHSA (Eq. 3 specifies
`BN(TDC(·))`); the block-level Add&Norm uses LayerNorm per Sec. 3.1.

**ST-FF**

```
Conv3d 1×1×1 → BN → GELU → depthwise Conv3d 3×3×3 → BN → GELU → Conv3d 1×1×1
```

**Loss** (Eq. 7)

```
total = α·NegPearson(time) + β·(FreqCE + LabelDistrib)
β = β₀·η^((epoch−1)/epochs)     1→5,  α=0.1
```

The live webapp runs a smaller config — dim=48, depth=6, 96 frames @96px →
216 tokens, 1.11M params.

## Usage

```bash
pip install -r requirements.txt
python train.py --data-root /path/to/preprocessed/dataset
```

## Default hyperparameters (paper Sec. 4.2)

N=12 transformer layers, h=4 heads, D=96, D'=144, theta=0.7, tau=2.0,
tube size 4x4x4, alpha=0.1, beta in [1,5] with exponential increment
(eta=5.0), sigma=1.0 for label distribution learning.

Note: video preprocessing (face detection/cropping with MTCNN, PPG/HR
ground-truth extraction) is dataset-specific and not included — `dataset.py`
only defines the loader interface the training loop expects.
