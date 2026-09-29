"""
PhysFormer: Facial Video-based Physiological Measurement with Temporal
Difference Transformer (Yu et al., CVPR 2022).

Implements the architecture from the paper: a shallow conv stem, a tube
tokenizer, N temporal difference transformer blocks (Temporal Difference
Multi-head Self-Attention + Spatio-temporal Feed-Forward), and an rPPG
predictor head that regresses a 1D signal from the video input.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class CDC_T(nn.Module):
    """Temporal Difference Convolution (TDC), Eq. (2) in the paper.

    Combines a vanilla 3D convolution with a temporal-difference term
    (weighted by theta) that subtracts the center-pixel response scaled by
    the summed kernel weights of the two temporal neighbors.
    """

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1,
                 padding=1, dilation=1, groups=1, bias=False, theta=0.7):
        super().__init__()
        self.conv = nn.Conv3d(
            in_channels, out_channels, kernel_size=kernel_size, stride=stride,
            padding=padding, dilation=dilation, groups=groups, bias=bias,
        )
        self.theta = theta

    def forward(self, x):
        out_normal = self.conv(x)
        if abs(self.theta) < 1e-8:
            return out_normal
        C_out, C_in, t, kh, kw = self.conv.weight.shape
        if t != 3:
            return out_normal
        kernel_diff = (
            self.conv.weight[:, :, 0, :, :].sum(dim=(2, 3))
            + self.conv.weight[:, :, 2, :, :].sum(dim=(2, 3))
        )
        kernel_diff = kernel_diff[:, :, None, None, None]
        out_diff = F.conv3d(
            x, kernel_diff, bias=None, stride=self.conv.stride, padding=0,
            dilation=self.conv.dilation, groups=self.conv.groups,
        )
        return out_normal - self.theta * out_diff


class Stem(nn.Module):
    """Shallow conv stem: 3 conv blocks with kernels (1x5x5),(3x3x3),(3x3x3).

    Each block is Conv3d -> BN -> ReLU -> MaxPool (spatial-only halving),
    so overall spatial dims are reduced by 8x while T is preserved.
    """

    def __init__(self, in_channels=3, dim=96):
        super().__init__()

        def block(cin, cout, k):
            pad = tuple(ks // 2 for ks in k)
            return nn.Sequential(
                nn.Conv3d(cin, cout, kernel_size=k, stride=1, padding=pad, bias=False),
                nn.BatchNorm3d(cout),
                nn.ReLU(inplace=True),
                nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2)),
            )

        self.net = nn.Sequential(
            block(in_channels, dim, (1, 5, 5)),
            block(dim, dim, (3, 3, 3)),
            block(dim, dim, (3, 3, 3)),
        )

    def forward(self, x):
        return self.net(x)


class TubeTokenizer(nn.Module):
    """Non-overlapping tube tokenization via a strided Conv3d, Eq. (1)."""

    def __init__(self, dim, tube_size=(4, 4, 4)):
        super().__init__()
        self.proj = nn.Conv3d(dim, dim, kernel_size=tube_size, stride=tube_size)

    def forward(self, x):
        return self.proj(x)


def vid2seq(x):
    """B,D,T,H,W -> B,(T*H*W),D"""
    b, d, t, h, w = x.shape
    return x.flatten(2).transpose(1, 2), (t, h, w)


def seq2vid(x, shape):
    """B,(T*H*W),D -> B,D,T,H,W"""
    t, h, w = shape
    b, n, d = x.shape
    return x.transpose(1, 2).reshape(b, d, t, h, w)


class TD_MHSA(nn.Module):
    """Temporal Difference Multi-head Self-Attention (Eqs. 3-5)."""

    def __init__(self, dim, heads=4, theta=0.7, tau=2.0):
        super().__init__()
        self.heads = heads
        self.dh = dim // heads
        self.tau = tau

        self.q_tdc = CDC_T(dim, dim, kernel_size=3, stride=1, padding=1, theta=theta)
        self.q_bn = nn.BatchNorm3d(dim)
        self.k_tdc = CDC_T(dim, dim, kernel_size=3, stride=1, padding=1, theta=theta)
        self.k_bn = nn.BatchNorm3d(dim)
        self.v_proj = nn.Conv3d(dim, dim, kernel_size=1)

        self.out_proj = nn.Linear(dim, dim)

    def forward(self, x):
        # x: B,D,T,H,W
        q = self.q_bn(self.q_tdc(x))
        k = self.k_bn(self.k_tdc(x))
        v = self.v_proj(x)

        q, shape = vid2seq(q)
        k, _ = vid2seq(k)
        v, _ = vid2seq(v)

        b, n, d = q.shape
        h, dh = self.heads, self.dh
        q = q.reshape(b, n, h, dh).permute(0, 2, 1, 3)
        k = k.reshape(b, n, h, dh).permute(0, 2, 1, 3)
        v = v.reshape(b, n, h, dh).permute(0, 2, 1, 3)

        attn = torch.matmul(q, k.transpose(-2, -1)) / self.tau
        attn = attn.softmax(dim=-1)
        out = torch.matmul(attn, v)  # B,h,N,dh

        out = out.permute(0, 2, 1, 3).reshape(b, n, d)
        out = self.out_proj(out)
        out = seq2vid(out, shape)
        return out


class ST_FF(nn.Module):
    """Spatio-temporal Feed-Forward: 1x1x1 -> depthwise 3x3x3 -> 1x1x1."""

    def __init__(self, dim, hidden_dim):
        super().__init__()
        self.fc1 = nn.Conv3d(dim, hidden_dim, kernel_size=1)
        self.bn1 = nn.BatchNorm3d(hidden_dim)
        self.dw = nn.Conv3d(hidden_dim, hidden_dim, kernel_size=3, padding=1, groups=hidden_dim)
        self.bn2 = nn.BatchNorm3d(hidden_dim)
        self.fc2 = nn.Conv3d(hidden_dim, dim, kernel_size=1)
        self.act = nn.GELU()

    def forward(self, x):
        x = self.act(self.bn1(self.fc1(x)))
        x = self.act(self.bn2(self.dw(x)))
        x = self.fc2(x)
        return x


class LayerNorm3d(nn.Module):
    """LayerNorm over the channel dim of a B,D,T,H,W tensor (token-wise,
    independent of batch composition) -- matches the paper's "Add & Norm"
    (LN), as distinct from the BN used inside TD-MHSA's Q/K path (Eq. 3).
    """

    def __init__(self, dim):
        super().__init__()
        self.norm = nn.LayerNorm(dim)

    def forward(self, x):
        x = x.permute(0, 2, 3, 4, 1)
        x = self.norm(x)
        return x.permute(0, 4, 1, 2, 3)


class TemporalDifferenceTransformerBlock(nn.Module):
    def __init__(self, dim, hidden_dim, heads=4, theta=0.7, tau=2.0, norm_type="ln"):
        super().__init__()
        self.attn = TD_MHSA(dim, heads=heads, theta=theta, tau=tau)
        self.ff = ST_FF(dim, hidden_dim)
        if norm_type == "ln":
            self.norm1 = LayerNorm3d(dim)
            self.norm2 = LayerNorm3d(dim)
        elif norm_type == "bn":
            # Legacy option: matches checkpoints trained before the fix to
            # match the paper's specified LayerNorm Add&Norm (see LayerNorm3d).
            self.norm1 = nn.BatchNorm3d(dim)
            self.norm2 = nn.BatchNorm3d(dim)
        else:
            raise ValueError(f"unknown norm_type: {norm_type}")

    def forward(self, x):
        x = self.norm1(x + self.attn(x))
        x = self.norm2(x + self.ff(x))
        return x


class PredictorHead(nn.Module):
    """Temporally upsamples to T, spatially averages, projects to 1D signal."""

    def __init__(self, dim, target_len):
        super().__init__()
        self.target_len = target_len
        self.proj = nn.Sequential(
            nn.Conv1d(dim, dim // 2, kernel_size=3, padding=1),
            nn.BatchNorm1d(dim // 2),
            nn.ELU(inplace=True),
            nn.Conv1d(dim // 2, 1, kernel_size=3, padding=1),
        )

    def forward(self, x):
        # x: B,D,T',H',W' -> spatial average -> B,D,T'
        b, d, t, h, w = x.shape
        x = x.mean(dim=(3, 4))
        x = F.interpolate(x, size=self.target_len, mode="linear", align_corners=False)
        y = self.proj(x)  # B,1,T
        return y.squeeze(1)


class PhysFormer(nn.Module):
    """Full PhysFormer model.

    Args match the paper's default settings: N=12 layers, h=4 heads,
    D=96 embedding dim, D'=144 feed-forward hidden dim, theta=0.7, tau=2.0,
    tube size 4x4x4.
    """

    def __init__(self, dim=96, ff_hidden=144, depth=12, heads=4,
                 theta=0.7, tau=2.0, tube_size=(4, 4, 4), frames=160, norm_type="ln"):
        super().__init__()
        self.stem = Stem(in_channels=3, dim=dim)
        self.tokenizer = TubeTokenizer(dim, tube_size=tube_size)
        self.blocks = nn.ModuleList([
            TemporalDifferenceTransformerBlock(dim, ff_hidden, heads=heads, theta=theta, tau=tau, norm_type=norm_type)
            for _ in range(depth)
        ])
        self.head = PredictorHead(dim, target_len=frames)

    def forward(self, x):
        # x: B,3,T,H,W
        x = self.stem(x)
        x = self.tokenizer(x)
        for blk in self.blocks:
            x = blk(x)
        y = self.head(x)
        return y


if __name__ == "__main__":
    model = PhysFormer(frames=160)
    x = torch.randn(1, 3, 160, 128, 128)
    y = model(x)
    print(y.shape)  # expect (1, 160)
