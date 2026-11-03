"""Download UBFC-rPPG DATASET_2 (Bobbia et al., Pattern Recognition Letters 2017) from the authors' public Google Drive
folder (https://sites.google.com/view/ybenezeth/ubfcrppg) into data/raw/UBFC-rPPG/DATASET_2. Resumable.

Terms (readme.txt / Agreement.xlsx in the same folder): research use; facial images of DATASET_2 subjects 21 and 27
must not be included in any publication, presentation or report.

    python -m bench.download_ubfc [--dataset DATASET_2]          (from rppg1/)
"""
import argparse
import os
import time

import gdown

from bench.preprocess import ROOT

FOLDER = "https://drive.google.com/drive/folders/1o0XU4gTIo46YfwaWjIgbtCncc-oF44Xk"
OUT = os.path.join(ROOT, "data", "raw", "UBFC-rPPG")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="DATASET_2")
    a = ap.parse_args()
    files = [f for f in gdown.download_folder(FOLDER, skip_download=True, quiet=True)
             if f.path.startswith(a.dataset + os.sep) or f.path in ("readme.txt", "Agreement.xlsx")]
    print(f"{len(files)} files -> {OUT}", flush=True)
    t0, total = time.time(), 0
    for i, f in enumerate(files, 1):
        dest = os.path.join(OUT, f.path)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for attempt in range(5):
            try:
                gdown.download(id=f.id, output=dest + ".part", quiet=True, resume=True)
                os.replace(dest + ".part", dest)
                break
            except Exception as e:                       # Drive quota / network: wait and resume the partial file
                print(f"retry {attempt + 1} {f.path}: {e}", flush=True)
                time.sleep(60 * (attempt + 1))
        else:
            print(f"FAILED {f.path}", flush=True)
            continue
        total += os.path.getsize(dest)
        el = time.time() - t0
        print(f"[{i}/{len(files)}] {f.path}  {total / 1e9:.1f} GB in {el / 60:.0f} min "
              f"({total / 1e6 / max(el, 1):.1f} MB/s)", flush=True)
    print("DOWNLOAD DONE", flush=True)


if __name__ == "__main__":
    main()
