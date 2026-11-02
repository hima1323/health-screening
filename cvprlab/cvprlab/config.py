"""Every switch of the CVPR Lab pipeline, and the roadmap presets.

A preset is a set of overrides on CVPRLabConfig(); the phase-by-phase roadmap and the ablation table are the same
model under different flags (README: "Train" and "Ablate").
"""
from dataclasses import dataclass, field, replace


@dataclass
class CVPRLabConfig:
    frames: int = 160               # clip length T
    img_size: int = 128
    fps: float = 30.0               # default when no per-clip frame rate is given

    # (1) EST encoder: (1,3,3) spatial conv + (3,1,1) temporal difference conv per block, spatial /2 per block
    stem_channels: tuple = (24, 48, 96)
    dim: int = 96
    use_tdc: bool = True
    # TDC in the encoder's temporal convs (attention Q/K keep it either way). Off by default: the benchmark input is
    # already frame-differenced (DiffNormalized), and differencing it again in every stem block amplifies camera
    # noise - on MCD-rPPG phase2 held-out MAE went 11.13 (on) -> 3.49 (off). Turn on for raw-pixel input.
    stem_tdc: bool = False
    theta: float = 0.7

    # (2) Zero-FLOPs Axial Swapper
    use_zas: bool = True
    zas_ratio: float = 0.5
    zas_block: int = 1

    # (3) tube tokenizer + TD-MHSA transformer
    tube_size: tuple = (2, 4, 4)    # temporal stride 2, not 4: 7.5 Hz feature rate would alias the cardiac band
    depth: int = 4
    heads: int = 4
    tau: float = 2.0
    ff_hidden: int = 144
    use_slowfast: bool = False      # PhysFormer++ two-pathway variant
    fast_dim_ratio: float = 0.5

    # (0)/(3b) STMap branch + SDMU (Central / Ring PDC)
    use_stmap: bool = True
    roi_grid: int = 5
    stmap_depth: int = 4
    use_pdc: bool = True

    # (4) dual-stream confidence-gated exchange
    use_dceb: bool = True
    dceb_slots: int = 16

    # (5) adaptive spatial filter
    use_asf: bool = True

    # (6)/(7) FreqPhys: PBF -> PSM -> ASS, then time <-> frequency cross-domain fusion
    use_freq_denoiser: bool = True
    psm_bins: int = 20
    ass_temperature: float = 0.5
    band_hz: tuple = (0.66, 3.0)    # 40-180 bpm
    nfft_min: int = 256
    use_cross_domain: bool = True
    cross_domain_layers: int = 2

    # (8) physics-grounded gated TCN
    use_gtcn: bool = True
    gtcn_layers: int = 6
    gtcn_kernel: int = 3

    # (9) optional heads
    use_llm_head: bool = False
    llm_dim: int = 128
    llm_layers: int = 2
    llm_prototypes: int = 32
    llm_patch: int = 16
    use_diffusion: bool = False
    diffusion_steps: int = 1000
    ddim_steps: int = 20

    # (10) structured attention fusion decoder
    use_safd: bool = True
    decoder_queries: int = 8

    # loss: L = NegPearson + beta(epoch) * (lambda1 * freqCE + lambda2 * LD), beta = beta0 * eta^((epoch-1)/epochs)
    beta0: float = 1.0
    eta: float = 5.0
    lambda_ce: float = 1.0
    lambda_ld: float = 1.0

    name: str = field(default="custom")


_PHYSFORMER = dict(depth=12, use_zas=False, use_asf=False, use_gtcn=False, use_stmap=False, use_dceb=False,
                   use_safd=False, use_freq_denoiser=False, use_cross_domain=False)
_PHYSICS = dict(_PHYSFORMER, depth=4, use_zas=True, use_asf=True, use_gtcn=True)
_DUAL = dict(_PHYSICS, use_stmap=True, use_dceb=True, use_safd=True)
_FREQ = dict(_DUAL, use_freq_denoiser=True, use_cross_domain=True)

PRESETS = {
    "phase1_physformer": _PHYSFORMER,
    "phase1_physformerpp": dict(_PHYSFORMER, use_slowfast=True),
    "phase2_physics": _PHYSICS,
    "phase3_dualstream": _DUAL,
    "phase4_frequency": _FREQ,
    "phase4_diffusion": dict(_FREQ, use_diffusion=True),
    "phase5_full": dict(_FREQ, use_diffusion=True, use_llm_head=True),
    "edge": dict(_FREQ, stem_channels=(16, 32, 48), dim=48, ff_hidden=72, depth=2, heads=4, stmap_depth=2,
                 cross_domain_layers=1, gtcn_layers=5),
}


def preset(name, **overrides):
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    return replace(CVPRLabConfig(), **{**PRESETS[name], **overrides}, name=name)
