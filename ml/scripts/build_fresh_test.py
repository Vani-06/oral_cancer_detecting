"""
Build an untouched final test set (review item 17).

Candidates: the older Kaggle "Oral Cancer" release (500 cancer / 250
non-cancer). Kept only if not a near-duplicate (24x24 greyscale thumbnail
cosine > 0.90) of ANY photo used anywhere so far -- Kaggle v2.0, client
cases, every split, the Mendeley sets, the user test folder -- and not a
near-duplicate of another kept candidate. Cancer-labelled candidates that
match an original-source benign lesion (Mendeley) are relabelled.

No model, threshold or calibration may be chosen with this set. It is
evaluated once, at the end, by scripts/review_analyses.py --final.

Usage:
    .venv/Scripts/python.exe -I scripts/build_fresh_test.py
"""

import csv
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
OUT = DATA / "fresh_test"


def thumb(path):
    with Image.open(path) as im:
        a = np.asarray(ImageOps.exif_transpose(im).convert("L").resize((24, 24)), dtype=np.float32)
    a = a - a.mean()
    return a.ravel() / (np.linalg.norm(a) + 1e-6)


def images(root):
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in EXTS)


def main():
    old = DATA / "kaggle_raw" / "Oral Cancer"
    candidates = images(old)
    seen_roots = [DATA / "kaggle_raw" / "Oral cancer Dataset 2.0", DATA / "client_cases", DATA / "case_split",
                  DATA / "case_split_fixed", DATA / "kaggle_split", DATA / "kaggle_split_fixed",
                  DATA / "external", DATA / "test_images", DATA / "client_validation", DATA / "client_holdout",
                  DATA / "combined_train", DATA / "combined_val"]
    seen = [p for r in seen_roots if r.exists() for p in images(r)]
    S = np.stack([thumb(p) for p in seen])
    C = np.stack([thumb(p) for p in candidates])
    benign = np.stack([thumb(p) for p in images(DATA / "external" / "mendeley_oral_images" / "benign")])

    novel = (C @ S.T).max(1) <= 0.90
    kept = []
    for i in np.where(novel)[0]:
        if all(float(C[i] @ C[j]) <= 0.90 for j in kept):
            kept.append(i)

    shutil.rmtree(OUT, ignore_errors=True)
    rows = []
    for i in kept:
        p = candidates[i]
        label = "Cancer" if p.parent.name.upper() == "CANCER" else "Non-Cancer"
        if label == "Cancer" and float((benign @ C[i]).max()) > 0.97:
            label = "Non-Cancer"
        dst = OUT / label / f"fresh_{len(rows):03d}{p.suffix.lower()}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        rows.append([dst.relative_to(OUT).as_posix(), label, p.relative_to(DATA).as_posix()])
    with open(OUT / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "label", "source"])
        w.writerows(rows)
    (OUT / "LOCKED.txt").write_text("Untouched final test set. Do not use for any model, threshold or calibration choice.\n")
    n_c = sum(r[1] == "Cancer" for r in rows)
    print(f"{len(candidates)} candidates; {int(novel.sum())} not seen before; {len(rows)} after removing duplicates "
          f"within the set: {n_c} cancer, {len(rows) - n_c} non-cancer")


if __name__ == "__main__":
    main()
