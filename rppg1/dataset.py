import os
import numpy as np
import torch
from torch.utils.data import Dataset
class PhysDataset(Dataset):
    def __init__(self, root, clip_len=160, img_size=128, augment=True):
        self.root = root
        self.samples = sorted(
            d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
        )
        self.clip_len = clip_len
        self.img_size = img_size
        self.augment = augment
    def __len__(self):
        return len(self.samples)
    def _load(self, name):
        d = os.path.join(self.root, name)
        frames = np.load(os.path.join(d, "frames.npy"))
        wave = np.load(os.path.join(d, "wave.npy"))
        hr = float(np.load(os.path.join(d, "hr.npy")))
        return frames, wave, hr
    def __getitem__(self, idx):
        frames, wave, hr = self._load(self.samples[idx])
        t = frames.shape[0]
        clip_len = min(self.clip_len, t)
        start = np.random.randint(0, t - clip_len + 1) if t > clip_len else 0
        frames = frames[start:start + clip_len]
        wave = wave[start:start + clip_len]
        if self.augment and np.random.rand() < 0.5:
            frames = frames[:, :, ::-1, :].copy()
        frames = frames.astype(np.float32) / 255.0
        frames = (frames - 0.5) / 0.5
        frames = torch.from_numpy(frames).permute(3, 0, 1, 2)  # C,T,H,W
        wave = torch.from_numpy(wave.astype(np.float32))
        hr = torch.tensor(hr, dtype=torch.float32)
        return frames, wave, hr
