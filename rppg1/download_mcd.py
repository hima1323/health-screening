import json
import os
import urllib.request

BASE = "https://huggingface.co/datasets/dypknu/mcd_rppg/resolve/main"
OUT_ROOT = os.path.join(os.path.dirname(__file__), "data", "raw_mcd")

with open("/tmp/download_list.txt") as f:
    paths = [line.strip() for line in f if line.strip()]

total = len(paths)
for i, path in enumerate(paths, 1):
    dest = os.path.join(OUT_ROOT, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        print(f"[{i}/{total}] skip (exists): {path}")
        continue
    url = f"{BASE}/{path}"
    try:
        urllib.request.urlretrieve(url, dest)
        size = os.path.getsize(dest)
        print(f"[{i}/{total}] {path} -> {size} bytes", flush=True)
    except Exception as e:
        print(f"[{i}/{total}] FAILED {path}: {e}", flush=True)

print("DOWNLOAD DONE")
