"""(5) Adaptive Spatial Filter (PHASE-Net): a per-frame softmax mask over spatial positions instead of global
average pooling, then the first-order temporal derivative is concatenated (the velocity term of the damped
oscillator in the GTCN) and projected back."""
import torch
import torch.nn as nn
import torch.nn.functional as F


class ASF(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.score = nn.Conv2d(dim, 1, 1)
        self.proj = nn.Conv1d(2 * dim, dim, 1)

    def mask(self, x):                     # (B,C,T,P) -> (B,T,P), sums to 1 over P
        return self.score(x).squeeze(1).softmax(dim=-1)

    def forward(self, x):
        h = torch.einsum("bctp,btp->bct", x, self.mask(x))
        dh = F.pad(h[:, :, 1:] - h[:, :, :-1], (1, 0))
        return self.proj(torch.cat([h, dh], 1))
