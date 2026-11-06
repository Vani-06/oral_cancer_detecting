"""
Distribution of the photo-quality measures (backend/app/services/photo_quality.py)
on real oral photos and on degraded copies, to choose the cut-offs.

    backend/.venv/Scripts/python.exe ml/scripts/photo_quality_stats.py --clinical "<clinical photos folder>"
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from gate_ood_test import DEGRADE, ROOT, folder  # noqa: E402
from app.services.photo_quality import measure  # noqa: E402


def summary(images):
    m = [measure(im) for im in images]
    return {k: {q: round(float(np.percentile([x[k] for x in m], q)), 4) for q in (0, 1, 2, 5, 50, 95, 99, 100)}
            for k in m[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clinical")
    args = ap.parse_args()
    test = folder(ROOT / "ml" / "data" / "kaggle_split_fixed" / "test")
    train = folder(ROOT / "ml" / "data" / "case_split_fixed" / "train")
    out = {"train oral": summary(train), "test oral": summary(test)}
    if args.clinical:
        out["clinical oral"] = summary(folder(args.clinical))
    for name, fn in DEGRADE.items():
        out[f"degraded: {name}"] = summary([fn(im) for im in test])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
