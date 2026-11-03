"""
Every standard screening metric for a cancer checkpoint, with 95% bootstrap
confidence intervals, on the corrected splits (scripts/fix_labels.py).

Binary (single answer at CANCER threshold 0.5): accuracy, sensitivity
(recall), specificity, precision (PPV), NPV, F1, balanced accuracy, MCC,
Cohen's kappa, ROC-AUC, PR-AUC, Brier score, expected calibration error.

Three-way (stability votes, thresholds from validation): coverage (share
decided), accuracy on decided cases, cancers called "no cancer" (the
dangerous error), non-cancers called "cancer", inconclusive rate.

Usage:
    .venv/Scripts/python.exe scripts/full_metrics.py [--checkpoint artifacts/resnet50_oral_cancer_v7.pt]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import (average_precision_score, brier_score_loss, cohen_kappa_score,
                             matthews_corrcoef, roc_auc_score)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402
from reference_experiments import STABILITY_EDITS  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
LO, HI = 0, 6  # votes out of 9: the thresholds chosen on validation in reference_experiments.py
# (its fractions 0.1111 / 0.5556 sit just above 1/9 and 5/9, so they mean 0 and 6 votes)


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b if b < 1 else p <= b)
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return total


def binary(y, p):
    pred = p >= 0.5
    tp, tn = (pred & y).sum(), (~pred & ~y).sum()
    fp, fn = (pred & ~y).sum(), (~pred & y).sum()
    sens, spec = tp / max(tp + fn, 1), tn / max(tn + fp, 1)
    prec, npv = tp / max(tp + fp, 1), tn / max(tn + fn, 1)
    return {
        "accuracy": (tp + tn) / len(y), "sensitivity": sens, "specificity": spec,
        "precision_ppv": prec, "npv": npv, "f1": 2 * prec * sens / max(prec + sens, 1e-9),
        "balanced_accuracy": (sens + spec) / 2, "mcc": matthews_corrcoef(y, pred),
        "cohen_kappa": cohen_kappa_score(y, pred), "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p), "brier": brier_score_loss(y, p), "ece": ece(y, p),
    }


def three_way(y, votes):
    d = np.where(votes >= HI, 1, np.where(votes <= LO, 0, -1))
    dec = d >= 0
    return {
        "coverage": dec.mean(), "inconclusive": 1 - dec.mean(),
        "decided_accuracy": (d[dec] == y[dec]).mean(),
        "cancers_called_no_cancer": (d[y] == 0).mean(), "cancers_called_cancer": (d[y] == 1).mean(),
        "noncancer_called_cancer": (d[~y] == 1).mean(), "noncancer_called_no_cancer": (d[~y] == 0).mean(),
    }


def with_ci(fn, y, *arrays, n=2000, seed=0):
    point = fn(y, *arrays)
    rng = np.random.default_rng(seed)
    boots = {k: [] for k in point}
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].all() or (~y[idx]).all():
            continue
        for k, v in fn(y[idx], *[a[idx] for a in arrays]).items():
            boots[k].append(v)
    return {k: {"value": float(v), "ci95": [float(np.percentile(boots[k], 2.5)), float(np.percentile(boots[k], 97.5))]}
            for k, v in point.items()}


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt"))
    args = ap.parse_args()
    model = st.load_model(Path(args.checkpoint))
    out = {}
    for name, root in [("validation", DATA / "case_split_fixed" / "val"), ("test", DATA / "kaggle_split_fixed" / "test")]:
        ims, y = labelled(root)
        p = st.run(*model, ims)[0]
        votes = np.sum([st.run(*model, [e(im) for im in ims])[0] >= 0.5 for e in STABILITY_EDITS], 0)
        out[name] = {"photos": int(len(y)), "cancers": int(y.sum()),
                     "binary": with_ci(binary, y, p), "three_way": with_ci(three_way, y, votes)}
        print(f"\n== {name} ({len(y)} photos, {y.sum()} cancers)")
        for group in ("binary", "three_way"):
            for k, v in out[name][group].items():
                print(f"  {group:9s} {k:28s} {v['value']:.3f}  [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]")
    hold = [st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
            for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv"))]
    ph = st.run(*model, hold)[0]
    out["client_holdout_specificity"] = float((ph < 0.5).mean())
    print(f"\nclient held-out dysplasia (39 photos, no cancer): specificity {out['client_holdout_specificity']:.3f}")
    (ML_DIR / "artifacts" / "full_metrics_v7.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
