"""(0) STMap: the face divided into a grid x grid set of ROIs, each ROI's colour averaged per frame, as 6 channels
(RGB + a YUV copy, MSTmap-style) x T x ROIs. Averaging the pixels of an ROI suppresses camera shot noise; each ROI
row is min-max normalised over time, which removes static skin tone and leaves the pulsation.

Two builders that must agree: numpy (data loading) and torch (on-device / tests).
"""
import numpy as np
import torch
import torch.nn.functional as F

YUV = np.array([[0.299, 0.587, 0.114], [-0.14713, -0.28886, 0.436], [0.615, -0.51499, -0.10001]], np.float32)


def _normalise(m, axis):
    lo, hi = m.min(axis=axis, keepdims=True), m.max(axis=axis, keepdims=True)
    return (m - lo) / np.maximum(hi - lo, 1e-6)


def build_stmap(frames, grid=5):
    """frames (T,H,W,3) RGB uint8/float -> (6,T,grid*grid) float32 in [0,1]."""
    f = np.asarray(frames, np.float32)
    t, h, w, _ = f.shape
    hc, wc = h // grid * grid, w // grid * grid
    rgb = f[:, :hc, :wc].reshape(t, grid, hc // grid, grid, wc // grid, 3).mean(axis=(2, 4)).reshape(t, -1, 3)
    m = np.concatenate([rgb, rgb @ YUV.T], -1)                       # (T,R,6)
    return np.ascontiguousarray(_normalise(m, 0).transpose(2, 0, 1))


def build_stmap_torch(frames, grid=5):
    """frames (B,T,H,W,3) tensor -> (B,6,T,grid*grid)."""
    f = frames.float()
    b, t, h, w, _ = f.shape
    hc, wc = h // grid * grid, w // grid * grid
    x = f[:, :, :hc, :wc].permute(0, 1, 4, 2, 3).reshape(b * t, 3, hc, wc)
    rgb = F.avg_pool2d(x, (hc // grid, wc // grid)).reshape(b, t, 3, -1).permute(0, 1, 3, 2)   # (B,T,R,3)
    m = torch.cat([rgb, rgb @ torch.from_numpy(YUV).T.to(rgb)], -1)
    lo, hi = m.amin(1, keepdim=True), m.amax(1, keepdim=True)
    return ((m - lo) / (hi - lo).clamp_min(1e-6)).permute(0, 3, 1, 2)
