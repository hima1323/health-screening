"""(1) Efficient Spatio-Temporal video encoder and (3b) SDMU STMap encoder."""
import torch.nn as nn

from cvprlab.modules.pdc import SDMUBlock
from cvprlab.modules.tdc import TDC


class ESTBlock(nn.Module):
    """(1,3,3) spatial conv -> (3,1,1) temporal difference conv -> spatial max-pool /2. Every frame is kept.
    Factorising 3x3x3 this way costs 9 + 3 = 12 MACs per output instead of 27."""

    def __init__(self, cin, cout, theta):
        super().__init__()
        self.spatial = nn.Sequential(nn.Conv3d(cin, cout, (1, 3, 3), padding=(0, 1, 1), bias=False),
                                     nn.BatchNorm3d(cout), nn.ReLU(inplace=True))
        self.temporal = TDC(cout, cout, (3, 1, 1), theta=theta)
        self.bn = nn.BatchNorm3d(cout)
        self.pool = nn.MaxPool3d((1, 2, 2))

    def forward(self, x):
        return self.pool(self.bn(self.temporal(self.spatial(x))).relu())


class ESTEncoder(nn.Module):
    """(B,3,T,S,S) -> (B,dim,T,S/8,S/8)"""

    def __init__(self, cfg):
        super().__init__()
        chans = (3,) + tuple(cfg.stem_channels)
        theta = cfg.theta if cfg.use_tdc and cfg.stem_tdc else 0.0
        self.blocks = nn.Sequential(*[ESTBlock(a, b, theta) for a, b in zip(chans[:-1], chans[1:])])
        self.proj = nn.Identity() if chans[-1] == cfg.dim else nn.Conv3d(chans[-1], cfg.dim, 1)

    def forward(self, x):
        return self.proj(self.blocks(x))


class SDMUEncoder(nn.Module):
    """STMap (B,6,T,R) -> (B,dim,T,R); a 2-D image whose axes are time and ROI index."""

    def __init__(self, cfg):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv2d(6, cfg.dim, 3, padding=1, bias=False), nn.BatchNorm2d(cfg.dim),
                                  nn.ReLU(inplace=True))
        self.blocks = nn.Sequential(*[SDMUBlock(cfg.dim, use_pdc=cfg.use_pdc) for _ in range(cfg.stmap_depth)])

    def forward(self, s):
        return self.blocks(self.stem(s))
