"""Checks the architecture's claims, not just that tensors flow.

    python -m pytest tests -q          (from cvprlab/)
"""
import math
import os
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cvprlab import PRESETS, CVPRLab, CVPRLabConfig, preset  # noqa: E402
from cvprlab.data.stmap import build_stmap, build_stmap_torch  # noqa: E402
from cvprlab.losses import cvprlab_loss, curriculum_beta  # noqa: E402
from cvprlab.modules.asf import ASF  # noqa: E402
from cvprlab.modules.freq import FreqDenoiser  # noqa: E402
from cvprlab.modules.gtcn import GTCN  # noqa: E402
from cvprlab.modules.pdc import RingPDC  # noqa: E402
from cvprlab.modules.tdc import TDC  # noqa: E402
from cvprlab.modules.zas import ZAS  # noqa: E402
from cvprlab.utils import count_macs  # noqa: E402

torch.manual_seed(0)
SMALL = dict(frames=64, img_size=64)


def inputs(cfg, b=1):
    return (torch.randn(b, 3, cfg.frames, cfg.img_size, cfg.img_size), torch.rand(b, 6, cfg.frames, 25),
            torch.full((b,), 30.0))


def test_zas_is_its_own_inverse():
    z = ZAS(96)
    x = torch.randn(2, 96, 4, 16, 16)
    assert torch.equal(z(z(x)), x)
    assert not torch.equal(z(x), x)
    assert len(z.idx) == 48


def test_zas_adds_zero_macs():
    cfg_on, cfg_off = preset("phase2_physics", **SMALL), preset("phase2_physics", use_zas=False, **SMALL)
    a, b = CVPRLab(cfg_on), CVPRLab(cfg_off)
    assert count_macs(a, *inputs(cfg_on)) == count_macs(b, *inputs(cfg_off))
    assert sum(p.numel() for p in a.parameters()) == sum(p.numel() for p in b.parameters())


def test_tdc_reduces_to_conv_at_theta_zero_and_cancels_neighbours_on_static_video():
    t0 = TDC(4, 4, (3, 1, 1), theta=0.0)
    x = torch.randn(1, 4, 8, 5, 5)
    assert torch.allclose(t0(x), t0.conv(x))
    t1 = TDC(4, 4, (3, 1, 1), theta=1.0)        # static video: the neighbour taps cancel, only the centre tap is left
    still = torch.randn(1, 4, 1, 5, 5).expand(1, 4, 8, 5, 5).contiguous()
    centre = torch.nn.functional.conv3d(still, t1.conv.weight[:, :, 1:2])
    assert torch.allclose(t1(still)[:, :, 1:-1], centre[:, :, 1:-1], atol=1e-5)


def test_gtcn_is_strictly_causal():
    g = GTCN(CVPRLabConfig()).eval()
    x = torch.randn(1, 96, 160)
    y = g(x)
    x2 = x.clone()
    x2[..., 100:] += torch.randn_like(x2[..., 100:])
    y2 = g(x2)
    assert torch.allclose(y[..., :100], y2[..., :100], atol=1e-6)
    assert not torch.allclose(y[..., 100:], y2[..., 100:])
    assert g.receptive_field == 127


def test_bandpass_rejects_out_of_band_by_four_orders():
    cfg = CVPRLabConfig(dim=4)
    den = FreqDenoiser(cfg, use_psm=False, use_ass=False)
    n, fs = 256, 30.0
    t = torch.arange(n) / fs
    inband = torch.sin(2 * math.pi * (10 * fs / n) * t)          # 1.17 Hz, on a bin
    outband = torch.sin(2 * math.pi * (40 * fs / n) * t)         # 4.69 Hz, on a bin
    fps = torch.tensor([fs])
    y_in, _ = den(inband.expand(1, 4, n).contiguous(), fps)
    y_out, _ = den(outband.expand(1, 4, n).contiguous(), fps)
    assert (y_out ** 2).sum() / (y_in ** 2).sum() < 1e-4
    assert torch.allclose(y_in, inband.expand(1, 4, n), atol=1e-4)


def test_spectrum_tokens_have_fixed_count_at_any_frame_rate():
    cfg = CVPRLabConfig(dim=8)
    den = FreqDenoiser(cfg)
    for fs in (21.0, 24.0, 30.0):
        y, tok = den(torch.randn(2, 8, 160), torch.full((2,), fs))
        assert y.shape == (2, 8, 160) and tok.shape == (2, cfg.psm_bins, 16)


def test_ring_pdc_is_blind_to_dc():
    r = RingPDC(3, 5)
    assert torch.allclose(r.kernel().sum(dim=(2, 3)), torch.zeros(5, 3), atol=1e-6)
    x = torch.randn(1, 3, 10, 10)
    assert torch.allclose(r(x + 7.0)[..., 1:-1, 1:-1], r(x)[..., 1:-1, 1:-1], atol=1e-4)


def test_asf_mask_is_a_distribution():
    a = ASF(8)
    m = a.mask(torch.randn(2, 8, 20, 16))
    assert torch.allclose(m.sum(-1), torch.ones(2, 20), atol=1e-6) and (m >= 0).all()


def test_stmap_builders_agree():
    frames = np.random.randint(0, 256, (40, 64, 64, 3), dtype=np.uint8)
    a = build_stmap(frames)
    b = build_stmap_torch(torch.from_numpy(frames)[None])[0].numpy()
    assert a.shape == (6, 40, 25)
    assert np.allclose(a, b, atol=1e-4)
    assert a.min() >= 0 and a.max() <= 1


def test_curriculum_ramps_from_beta0_to_eta():
    assert curriculum_beta(1, 10) == pytest.approx(1.0)
    assert curriculum_beta(11, 10) == pytest.approx(5.0)
    assert curriculum_beta(5, 10) < curriculum_beta(6, 10)


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_preset_runs_and_backpropagates(name):
    cfg = preset(name, **SMALL)
    m = CVPRLab(cfg).train()
    v, s, fps = inputs(cfg, b=2)
    y = m(v, s, fps)
    assert y.shape == (2, cfg.frames) and torch.isfinite(y).all()
    hr = torch.tensor([72.0, 90.0])
    z = (y - y.mean(1, keepdim=True)) / (y.std(1, keepdim=True) + 1e-8)
    loss, _ = cvprlab_loss(z, torch.randn(2, cfg.frames), hr, fps, 1, 10, cfg)
    if m.diffusion is not None:
        _, h = m(v, s, fps, return_features=True)
        loss = loss + m.diffusion.loss(h, y.detach(), z.detach())
    loss.backward()
    grads = [p.grad for p in m.parameters() if p.grad is not None]
    assert len(grads) > 0.9 * sum(1 for _ in m.parameters())
    assert all(bool(torch.isfinite(g).all()) for g in grads)
    m.eval()
    with torch.no_grad():
        assert m(v, s, fps).shape == (2, cfg.frames)
