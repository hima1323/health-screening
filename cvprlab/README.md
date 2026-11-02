# CVPR Lab — unified rPPG architecture

A from-scratch PyTorch implementation of the unified rPPG model described in the report
*"rPPG Model Architecture Report: PhysFormer → PhysFormer++ → PhysLLM → PhysNeXt → FreqPhys → PHASE-Net"*.
Every stage is a config flag ([config.py](cvprlab/config.py)), so the roadmap phases and the ablation table are one
code path.

```
video ─┬─▶ EST encoder (TDC) ─▶ ZAS ─▶ tube tokens ─▶ TD-transformer ─┐
       │                                                              ├─▶ DCEB ─▶ ASF ─▶ fuse
       └─▶ STMap (ROI pooling) ─────▶ SDMU (Central/Ring PDC) ────────┘                  │
                                                                                         ▼
   waveform ◀── SAFD decoder ◀── [diffusion] ◀── [LLM head] ◀── GTCN ◀── cross-domain ◀── PBF▸PSM▸ASS
```

| # | Stage | Paper | Code |
|---|---|---|---|
| ⓪ | Dual input: video + STMap (5×5 ROIs, RGB+YUV, min-max per ROI) | PhysNeXt | [data/stmap.py](cvprlab/data/stmap.py) |
| ① | EST encoder: (1,3,3) conv + (3,1,1) temporal difference conv | PHASE-Net, PhysFormer | [encoders.py](cvprlab/encoders.py), [tdc.py](cvprlab/modules/tdc.py) |
| ② | Zero-FLOPs Axial Swapper | PHASE-Net | [zas.py](cvprlab/modules/zas.py) |
| ③ | Tube tokenizer (2,4,4) + TD-MHSA (τ = 2) + ST-FF | PhysFormer | [transformer.py](cvprlab/modules/transformer.py) |
| ③ | SlowFast two-pathway transformer *(opt.)* | PhysFormer++ | [transformer.py](cvprlab/modules/transformer.py) |
| ③ᵇ | SDMU: vanilla + Central-PDC + Ring-PDC | PhysNeXt | [pdc.py](cvprlab/modules/pdc.py) |
| ④ | Dual-stream confidence-gated exchange (slots, band confidence, spectral match, gate, reliability) | PhysNeXt | [dceb.py](cvprlab/modules/dceb.py) |
| ⑤ | Adaptive spatial filter + temporal derivative | PHASE-Net | [asf.py](cvprlab/modules/asf.py) |
| ⑥ | PBF → PSM → ASS frequency denoiser | FreqPhys | [freq.py](cvprlab/modules/freq.py) |
| ⑦ | Time ⇄ frequency cross-domain fusion | FreqPhys | [freq.py](cvprlab/modules/freq.py) |
| ⑧ | Physics-grounded causal gated TCN (dilations 1…32, RF 127) | PHASE-Net | [gtcn.py](cvprlab/modules/gtcn.py) |
| ⑨ | DDS + Text Prototype Guidance + pluggable LM *(opt.)* | PhysLLM | [llm_head.py](cvprlab/modules/llm_head.py) |
| ⑨ᵇ | Frequency-conditioned diffusion refiner, DDIM sampling *(opt.)* | FreqPhys | [diffusion.py](cvprlab/modules/diffusion.py) |
| ⑩ | Structured attention fusion decoder (state + query tokens, log-reliability bias) | PhysNeXt | [decoder.py](cvprlab/modules/decoder.py) |
| — | NegPearson + β(epoch)·(freq-CE + label distribution), β = β₀·η^((e−1)/E) | PhysFormer | [losses.py](cvprlab/losses.py) |

## Presets

| Preset | Contents | Params (this code) |
|---|---|---|
| `phase1_physformer` | PhysFormer baseline: TD-transformer video branch, depth 12 | 6.99 M |
| `phase1_physformerpp` | + SlowFast two-pathway transformer | 9.51 M |
| `phase2_physics` | depth 4 + ZAS + ASF + physics GTCN | 3.07 M |
| `phase3_dualstream` | + STMap branch, DCEB, SAFD decoder | 4.49 M |
| `phase4_frequency` | + PBF/PSM/ASS and cross-domain fusion | 4.82 M |
| `phase4_diffusion` | + frequency-conditioned diffusion refiner | 4.90 M |
| `phase5_full` | + LLM context head | 5.70 M |
| `edge` | small deployment variant (dim 48, no diffusion / LLM) | 0.76 M |

All presets fit a 6 GB GPU at batch 1 with fp16 (peak 0.9–3.8 GB at 160×128×128).

## Training and benchmarking

Training runs through the shared rPPG benchmark harness in `../rppg1/bench`, so CVPR Lab and the rppg1 PhysFormer
are trained and tested under the identical protocol (subject-disjoint split, DiffNormalized input and label,
whole-video FFT heart rate):

```bash
cd ../rppg1
python -m bench.run train --arch cvprlab:phase4_frequency --train mcd_IriunWebcam --test mcd_IriunWebcam
python -m bench.run test  --arch cvprlab:phase4_frequency --ckpt runs/<run>/best.pt --test ubfc
python -m bench.ladder    # phase1 -> phase4 on MCD-rPPG, each also tested on UBFC-rPPG
```

The model takes `model(video, stmap, fps)`: `fps` is per clip because MCD-rPPG is ~24 fps and UBFC-rPPG 30 fps,
and the frequency stages (PBF/PSM/ASS, DCEB confidence, frequency losses) work in physical Hz.

## Tests

```bash
python -m pytest tests -q        # 18 tests
```

They check the claims, not just shapes: ZAS adds zero MACs and is its own inverse; TDC is a plain conv at θ = 0 and
cancels the neighbour taps on a static video; the GTCN is strictly causal with a 127-sample receptive field; the
bandpass rejects out-of-band energy by more than four orders of magnitude; spectrum tokens have a fixed count at
21, 24 and 30 fps; Ring-PDC is blind to DC; the ASF mask is a distribution; the numpy and torch STMap builders
agree; the curriculum ramps β from β₀ to η·β₀; every preset runs, back-propagates with finite gradients, and
evaluates.

## Design decisions

* **No temporal difference conv in the encoder stem by default** (`stem_tdc=False`; attention Q/K keep TDC).
  The benchmark feeds DiffNormalized frames, which are already a temporal difference; differencing again in every
  stem block approximates a second derivative and amplifies camera noise. Measured on MCD-rPPG (phase2, 20
  held-out subjects): stem TDC on → MAE 11.13, r −0.04; off → MAE 3.49, r 0.52. Fixed curriculum weights instead
  (η = 1) did not help (10.88), so the loss was ruled out first. Turn `stem_tdc` on for raw-pixel input.
* **Tube size (2,4,4)**, not (4,4,4): at 30 fps a temporal stride of 4 leaves 7.5 Hz features whose Nyquist limit
  (3.75 Hz) sits on the cardiac band's upper edge.
* **ZAS after the encoder**, not on raw RGB (3 channels have no meaningful fraction to swap).
* **The video branch is resampled to the full frame rate before DCEB**, so everything downstream runs at true fps.
* **PSM weights live on a fixed grid of 20 physical frequencies** (0.66–3.0 Hz) and are interpolated onto each
  clip's FFT bins, so one set of weights serves 24 and 30 fps; the frequency tokens for cross-domain fusion are
  sampled on the same grid.
* **Frequency stages run in float32** inside fp16 training (fp16 FFTs need power-of-two sizes and lose precision).
* **Attention is written out explicitly** (no `nn.MultiheadAttention`), keeping `torch.export` / ONNX possible.
* **Reliability biases attention additively** (`log r`), attenuating rather than dropping untrusted instants.

## Not included (yet)

The README's vitals layer (HRV, respiration, BP, SpO₂), Streamlit dashboard, oximeter reader, live webcam demo
and export scripts are not part of this package; the screening kiosk in `../reasoning_model` covers upload-based
measurement for now. No pretrained weights ship here: all accuracy numbers come from runs in `../rppg1/runs`.
