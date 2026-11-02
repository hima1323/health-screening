"""Parameter / MAC counting and latency."""
import time

import torch
from torch.utils.flop_counter import FlopCounterMode


def count_params(model):
    return sum(p.numel() for p in model.parameters())


@torch.no_grad()
def count_macs(model, *inputs):
    """Multiply-accumulates of one forward pass (FLOPs / 2, as counted by torch's flop counter)."""
    model.eval()
    with FlopCounterMode(display=False) as fc:
        model(*inputs)
    return fc.get_total_flops() // 2


@torch.no_grad()
def latency_ms(model, *inputs, warmup=2, runs=5):
    model.eval()
    for _ in range(warmup):
        model(*inputs)
    if inputs[0].is_cuda:
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(runs):
        model(*inputs)
    if inputs[0].is_cuda:
        torch.cuda.synchronize()
    return (time.perf_counter() - t0) / runs * 1000
