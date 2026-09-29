"""
Loss functions from the PhysFormer paper (Sec. 3.2, 3.3):
  - Negative Pearson loss (temporal domain)
  - Frequency cross-entropy loss (frequency domain)
  - Label distribution loss via KL divergence against a Gaussian label
    distribution centered at the ground-truth HR (Eq. 6)
  - Curriculum-learning guided dynamic combination (Eq. 7)
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class NegPearsonLoss(nn.Module):
    """Negative Pearson correlation loss between predicted and gt signals."""

    def forward(self, pred, target):
        pred = pred - pred.mean(dim=-1, keepdim=True)
        target = target - target.mean(dim=-1, keepdim=True)
        num = (pred * target).sum(dim=-1)
        den = torch.sqrt((pred ** 2).sum(dim=-1) * (target ** 2).sum(dim=-1) + 1e-8)
        r = num / den
        return (1 - r).mean()


def _psd(signal, fps, low_bpm=42, high_bpm=180, n_fft=None):
    """Compute a normalized power spectral density restricted to the
    physiologically plausible HR band [low_bpm, high_bpm], one bin per bpm.
    Returns a tensor of shape (B, L) with L = high_bpm - low_bpm + 1.
    """
    b, t = signal.shape
    n_fft = n_fft or max(t, 2048)
    signal = signal - signal.mean(dim=-1, keepdim=True)
    spec = torch.fft.rfft(signal, n=n_fft, dim=-1)
    power = spec.real ** 2 + spec.imag ** 2  # (B, n_fft//2+1)
    freqs = torch.fft.rfftfreq(n_fft, d=1.0 / fps).to(signal.device)  # Hz
    bpm = freqs * 60.0

    labels = torch.arange(low_bpm, high_bpm + 1, device=signal.device, dtype=torch.float32)
    # For each target bpm bin, take the closest FFT bin's power.
    idx = torch.argmin(torch.abs(bpm.unsqueeze(0) - labels.unsqueeze(1)), dim=1)  # (L,)
    psd = power[:, idx]  # (B, L)
    return psd


class FrequencyCrossEntropyLoss(nn.Module):
    """Cross-entropy loss over the PSD treated as class logits, with the
    ground-truth HR (bpm) as the target class, following [46, 63].
    """

    def __init__(self, fps=30, low_bpm=42, high_bpm=180):
        super().__init__()
        self.fps = fps
        self.low_bpm = low_bpm
        self.high_bpm = high_bpm

    def forward(self, pred_signal, hr_gt):
        psd = _psd(pred_signal, self.fps, self.low_bpm, self.high_bpm)
        target = (hr_gt.round().long() - self.low_bpm).clamp(0, psd.shape[1] - 1)
        return F.cross_entropy(psd, target)


class LabelDistributionLoss(nn.Module):
    """KL(p || softmax(psd)) with p a Gaussian label distribution centered
    at the ground-truth HR, Eq. (6).
    """

    def __init__(self, fps=30, low_bpm=42, high_bpm=180, sigma=1.0):
        super().__init__()
        self.fps = fps
        self.low_bpm = low_bpm
        self.high_bpm = high_bpm
        self.sigma = sigma

    def forward(self, pred_signal, hr_gt):
        psd = _psd(pred_signal, self.fps, self.low_bpm, self.high_bpm)
        L = psd.shape[1]
        k = torch.arange(self.low_bpm, self.high_bpm + 1, device=psd.device, dtype=torch.float32)
        k = k.unsqueeze(0).expand(psd.shape[0], -1)
        mu = hr_gt.unsqueeze(1).float()
        p = torch.exp(-((k - mu) ** 2) / (2 * self.sigma ** 2))
        p = p / p.sum(dim=1, keepdim=True)

        log_q = F.log_softmax(psd, dim=1)
        kl = F.kl_div(log_q, p, reduction="batchmean")
        return kl


class PhysFormerLoss(nn.Module):
    """Curriculum-learning guided dynamic loss, Eq. (7):

        L_overall = alpha * L_time + beta * (L_CE + L_LD)
        beta = beta0 * eta ** ((epoch_current - 1) / epoch_total)
    """

    def __init__(self, fps=30, low_bpm=42, high_bpm=180, sigma=1.0,
                 alpha=0.1, beta0=1.0, eta=5.0, epoch_total=25):
        super().__init__()
        self.time_loss = NegPearsonLoss()
        self.ce_loss = FrequencyCrossEntropyLoss(fps, low_bpm, high_bpm)
        self.ld_loss = LabelDistributionLoss(fps, low_bpm, high_bpm, sigma)
        self.alpha = alpha
        self.beta0 = beta0
        self.eta = eta
        self.epoch_total = epoch_total

    def beta(self, epoch_current):
        return self.beta0 * (self.eta ** ((epoch_current - 1) / self.epoch_total))

    def forward(self, pred_signal, target_signal, hr_gt, epoch_current):
        l_time = self.time_loss(pred_signal, target_signal)
        l_ce = self.ce_loss(pred_signal, hr_gt)
        l_ld = self.ld_loss(pred_signal, hr_gt)
        beta = self.beta(epoch_current)
        total = self.alpha * l_time + beta * (l_ce + l_ld)
        return total, {
            "loss_time": l_time.item(),
            "loss_ce": l_ce.item(),
            "loss_ld": l_ld.item(),
            "beta": beta,
            "loss_total": total.item(),
        }
