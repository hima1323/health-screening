"""The ten-stage CVPR Lab assembly. Every stage is switched by CVPRLabConfig (config.py)."""
import torch
import torch.nn as nn
import torch.nn.functional as F

from cvprlab.config import CVPRLabConfig
from cvprlab.encoders import ESTEncoder, SDMUEncoder
from cvprlab.modules.asf import ASF
from cvprlab.modules.dceb import DCEB
from cvprlab.modules.decoder import SAFD, ConvHead
from cvprlab.modules.diffusion import FreqDiffusion
from cvprlab.modules.freq import CrossDomain, FreqDenoiser
from cvprlab.modules.gtcn import GTCN
from cvprlab.modules.llm_head import LLMHead
from cvprlab.modules.transformer import SlowFastTransformer, TDTransformer
from cvprlab.modules.zas import ZAS


class CVPRLab(nn.Module):
    def __init__(self, cfg=None, llm_backbone=None):
        super().__init__()
        cfg = cfg or CVPRLabConfig()
        self.cfg = cfg
        d = cfg.dim
        side = cfg.img_size // 8 // cfg.tube_size[1]               # token grid side after encoder + tube
        self.encoder = ESTEncoder(cfg)
        self.zas = ZAS(d, cfg.zas_ratio, cfg.zas_block) if cfg.use_zas else None
        self.transformer = SlowFastTransformer(cfg) if cfg.use_slowfast else TDTransformer(cfg)
        self.asf_v = ASF(d) if cfg.use_asf else None
        if cfg.use_stmap:
            rois = cfg.roi_grid ** 2
            self.sdmu = SDMUEncoder(cfg)
            self.dceb = DCEB(cfg, side * side, rois) if cfg.use_dceb else None
            self.asf_s = ASF(d) if cfg.use_asf else None
            self.fuse = nn.Conv1d(2 * d, d, 1)
        self.denoiser = FreqDenoiser(cfg) if cfg.use_freq_denoiser else None
        self.cross = CrossDomain(cfg) if cfg.use_freq_denoiser and cfg.use_cross_domain else None
        self.gtcn = GTCN(cfg) if cfg.use_gtcn else None
        self.llm = LLMHead(cfg, llm_backbone) if cfg.use_llm_head else None
        self.diffusion = FreqDiffusion(cfg) if cfg.use_diffusion else None
        self.decoder = SAFD(cfg) if cfg.use_safd else ConvHead(d)

    @staticmethod
    def pool(x, asf):
        return asf(x) if asf is not None else x.mean(-1)

    def features(self, video, stmap=None, fps=None, prompt_embedding=None):
        """-> temporal features (B,C,T), reliability (B,T) or None, branch confidences (B,2) or None."""
        cfg = self.cfg
        b, _, t = video.shape[:3]
        fps = fps if fps is not None else torch.full((b,), cfg.fps, device=video.device)
        v = self.encoder(video)                                     # (B,C,T,S/8,S/8)
        if self.zas is not None:
            v = self.zas(v)
        v = self.transformer(v)                                     # (B,C,T/ts,h,w)
        c, tt = v.shape[1], v.shape[2]
        fv = F.interpolate(v.flatten(3).permute(0, 1, 3, 2).reshape(b, -1, tt), size=t, mode="linear",
                           align_corners=False).reshape(b, c, -1, t).permute(0, 1, 3, 2)   # (B,C,T,P) at full fps
        rel = conf = None
        if cfg.use_stmap:
            if stmap is None:
                raise ValueError("this configuration needs the STMap input")
            fs = self.sdmu(stmap)                                   # (B,C,T,R)
            if self.dceb is not None:
                fv, fs, conf, rel = self.dceb(fv, fs, fps)
            h = self.fuse(torch.cat([self.pool(fv, self.asf_v), self.pool(fs, self.asf_s)], 1))
        else:
            h = self.pool(fv, self.asf_v)
        if self.denoiser is not None:
            ht, spec = self.denoiser(h, fps)
            h = self.cross(ht.to(h.dtype), spec) if self.cross is not None else ht.to(h.dtype)
        if self.gtcn is not None:
            h = self.gtcn(h)
        if self.llm is not None:
            h = self.llm(h, fps, prompt_embedding)
        return h, rel, conf

    def forward(self, video, stmap=None, fps=None, prompt_embedding=None, return_features=False):
        """video (B,3,T,S,S), stmap (B,6,T,R), fps (B,) -> rPPG waveform (B,T)."""
        h, rel, conf = self.features(video, stmap, fps, prompt_embedding)
        y = self.decoder(h, rel, conf)
        if self.diffusion is not None and not self.training:
            y = self.diffusion.sample(h.float(), y.float())
        return (y, h) if return_features else y
