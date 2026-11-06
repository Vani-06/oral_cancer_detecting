"""
Per-fold variability of the grading cross-validation (review item 16).

Recomputes the folds of `train_grading.py cv` (StratifiedGroupKFold, 5
folds, shuffle, random_state 42 -- deterministic) and scores the saved
out-of-fold predictions fold by fold, per photo and per patient.

Usage:
    .venv/Scripts/python.exe scripts/grading_per_fold.py [--init imagenet]
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score
from sklearn.model_selection import StratifiedGroupKFold

ML_DIR = Path(__file__).resolve().parent.parent
GRADES = ["mild_dysplasia", "moderate_dysplasia", "severe_dysplasia"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", default="imagenet")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(ML_DIR / "artifacts" / f"grading_cv_{args.init}_predictions.csv")))
    y = np.array([GRADES.index(r["true_grade"]) for r in rows])
    groups = np.array([int(r["case_id"]) for r in rows])
    probs = np.array([[float(r[f"p_{g}"]) for g in GRADES] for r in rows])
    pred = probs.argmax(1)
    folds = []
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    for k, (_, te) in enumerate(splitter.split(np.zeros(len(y)), y, groups), 1):
        pat = sorted(set(groups[te]))
        pt = np.array([y[groups == g][0] for g in pat])
        pp = np.array([probs[groups == g].mean(0).argmax() for g in pat])
        folds.append({
            "fold": k, "photos": int(len(te)), "patients": len(pat),
            "photo_accuracy": float((pred[te] == y[te]).mean()),
            "photo_kappa": float(cohen_kappa_score(y[te], pred[te], weights="quadratic")),
            "patient_accuracy": float((pp == pt).mean()),
            "majority_baseline": float(np.bincount(y[te], minlength=3).max() / len(te)),
        })
    summary = {k: {"mean": float(np.mean([f[k] for f in folds])), "sd": float(np.std([f[k] for f in folds], ddof=1)),
                   "min": float(np.min([f[k] for f in folds])), "max": float(np.max([f[k] for f in folds]))}
               for k in ("photo_accuracy", "photo_kappa", "patient_accuracy", "majority_baseline")}
    out = {"folds": folds, "summary": summary}
    (ML_DIR / "artifacts" / f"grading_per_fold_{args.init}.json").write_text(json.dumps(out, indent=2))
    for f in folds:
        print(f"fold {f['fold']}: {f['patients']} patients, photo acc {f['photo_accuracy']:.3f}, kappa {f['photo_kappa']:.3f}, "
              f"patient acc {f['patient_accuracy']:.3f}, always-moderate {f['majority_baseline']:.3f}")
    for k, v in summary.items():
        print(f"{k:18s} mean {v['mean']:.3f} SD {v['sd']:.3f} (range {v['min']:.3f}-{v['max']:.3f})")


if __name__ == "__main__":
    main()
