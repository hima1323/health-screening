"""Stream UBFC-rPPG DATASET_2 from the authors' official OneDrive mirror into the preprocessed cache, deleting each raw
video once it is cached: download subject k+1 while subject k is preprocessed, so at most two raw videos (~3.7 GB)
are on disk and the cache ends at ~4 GB instead of 75 GB raw. Resumable (cached subjects are skipped; partial
downloads continue with HTTP Range).

Source: https://sites.google.com/view/ybenezeth/ubfcrppg ("Contact and download": Google Drive or OneDrive; the
Google Drive copy is often over its download quota). Terms (readme.txt / Agreement.xlsx): research use; facial
images of DATASET_2 subjects 21 and 27 must not appear in any publication, presentation or report.

    python -m bench.fetch_ubfc [--keep-raw]          (from rppg1/)
"""
import argparse
import os
import queue
import re
import threading
import time
import urllib.parse as up

import requests

from bench.preprocess import CACHE, ROOT, process
from bench.readers import ubfc_load

SHARE = ("https://univbourgogne-my.sharepoint.com/:f:/g/personal/yannick_benezeth_u-bourgogne_fr/"
         "IgDQvHIcDjiMSrzknzArGE25AVSjt4fjw11QgLpsJX2QPec?e=ySQtZt")
SITE = "https://univbourgogne-my.sharepoint.com/personal/yannick_benezeth_u-bourgogne_fr"
RAW = os.path.join(ROOT, "data", "raw", "UBFC-rPPG", "DATASET_2")
OUT = os.path.join(CACHE, "ubfc")


def session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    r = s.get(SHARE, allow_redirects=True, timeout=60)        # sets the anonymous-link FedAuth cookie
    return s, up.parse_qs(up.urlparse(r.url).query)["id"][0]


def ls(s, path):
    u = f"{SITE}/_api/web/GetFolderByServerRelativeUrl('{up.quote(path)}')?$expand=Folders,Files"
    r = s.get(u, headers={"Accept": "application/json;odata=nometadata"}, timeout=60)
    r.raise_for_status()
    return r.json()


def download(s, server_url, dest, size):
    """Stream one file with resume; returns bytes fetched in this call."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    url = f"{SITE}/_api/web/GetFileByServerRelativeUrl('{up.quote(server_url)}')/$value"
    for attempt in range(6):
        try:
            hdr = {"Range": f"bytes={have}-"} if have else {}
            with s.get(url, headers=hdr, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(part, "ab" if have and r.status_code == 206 else "wb") as f:
                    if r.status_code != 206:
                        have = 0
                    for chunk in r.iter_content(1 << 22):
                        f.write(chunk)
                        have += len(chunk)
            if have >= size:
                os.replace(part, dest)
                return size
        except (requests.RequestException, OSError) as e:
            print(f"retry {attempt + 1} {os.path.basename(dest)}: {e}", flush=True)
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"download failed: {server_url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-raw", action="store_true", help="do not delete vid.avi after caching")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    s, root = session()
    subjects = sorted(ls(s, root + "/DATASET_2")["Folders"], key=lambda f: int(re.sub(r"\D", "", f["Name"])))
    todo = [f for f in subjects if not os.path.isfile(os.path.join(OUT, f["Name"] + ".json"))]
    print(f"{len(subjects)} subjects, {len(subjects) - len(todo)} already cached -> {OUT}", flush=True)
    ready, t0, got = queue.Queue(maxsize=1), time.time(), [0]

    def downloader():
        for sub in todo:
            files = ls(s, sub["ServerRelativeUrl"])["Files"]
            for f in sorted(files, key=lambda f: f["Name"] != "ground_truth.txt"):
                dest = os.path.join(RAW, sub["Name"], f["Name"])
                if not (os.path.isfile(dest) and os.path.getsize(dest) == int(f["Length"])):
                    got[0] += download(s, f["ServerRelativeUrl"], dest, int(f["Length"]))
            ready.put(sub["Name"])                      # blocks while the previous subject is being preprocessed
        ready.put(None)

    th = threading.Thread(target=downloader, daemon=True)
    th.start()
    done = 0
    while (name := ready.get()) is not None:
        d = os.path.join(RAW, name)
        m = process({"dataset": "UBFC-rPPG", "video_id": name, "subject": int(re.sub(r"\D", "", name)), "dir": d},
                    ubfc_load, OUT)
        if m and not a.keep_raw:
            os.remove(os.path.join(d, "vid.avi"))      # the cache holds everything training needs
        done += 1
        el = time.time() - t0
        print(f"[{done}/{len(todo)}] {name}: {m['n_frames'] if m else 0} frames, face "
              f"{'found' if m and m['face_found'] else 'NOT found'}; downloaded {got[0] / 1e9:.1f} GB in "
              f"{el / 60:.0f} min ({got[0] / 1e6 / max(el, 1):.1f} MB/s)", flush=True)
    print("FETCH DONE", flush=True)


if __name__ == "__main__":
    main()
