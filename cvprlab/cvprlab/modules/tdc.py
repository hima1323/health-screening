"""Temporal Difference Convolution (PhysFormer, Yu et al. CVPR 2022, Eq. 2).

    y = Conv3d(x) - theta * (sum w[t-1] + sum w[t+1]) * x[t]

The subtracted term is the centre frame weighted by the summed kernel weights of its two temporal neighbours, so the
response is driven by frame-to-frame change rather than absolute brightness. theta = 0 is a plain convolution.
"""
import torch.nn as nn
import torch.nn.functional as F


class TDC(nn.Module):
    def __init__(self, cin, cout, kernel=(3, 1, 1), stride=1, theta=0.7, groups=1, bias=False):
        super().__init__()
        self.conv = nn.Conv3d(cin, cout, kernel, stride=stride, padding=tuple(k // 2 for k in kernel), groups=groups,
                              bias=bias)
        self.theta = theta

    def forward(self, x):
        out = self.conv(x)
        w = self.conv.weight
        if abs(self.theta) < 1e-8 or w.shape[2] != 3:
            return out
        kd = (w[:, :, 0].sum(dim=(2, 3)) + w[:, :, 2].sum(dim=(2, 3)))[:, :, None, None, None]
        return out - self.theta * F.conv3d(x, kd, stride=self.conv.stride, groups=self.conv.groups)
