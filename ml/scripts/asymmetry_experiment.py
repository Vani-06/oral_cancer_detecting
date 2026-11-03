"""
Proxy test for same-patient opposite-side comparison, using data we have.

A whole-mouth photo contains both sides of the same mouth, photographed with
the same camera and light. Compare the left half with the mirrored right half
in feature space (cosine distance of the cancer model's penultimate
features): a healthy mouth should be more symmetric than one with a
one-sided lesion.

Reports, on validation (selection) and the corrected Kaggle test split:
- AUC of the asymmetry score alone (cancer vs non-cancer)
- AUC of the model's P(Cancer) alone, and of both combined (logistic
  regression fitted on validation only, applied to test)
- the distribution of healthy-mouth asymmetry, used to calibrate the
  "no clear difference from the patient's own normal side" threshold.

Usage:
    .venv/Scripts/python.exe scripts/asymmetry_experiment.py [--checkpoint artifacts/resnet50_oral_cancer_v7.pt]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import ImageOps
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"


def halves(im):
    w, h = im.size
    left = im.crop((0, 0, w // 2, h))
    right = ImageOps.mirror(im.crop((w - w // 2, 0, w, h)))
    return left, right


def asymmetry(model, images):
    lefts, rights = zip(*(halves(im) for im in images))
    _, fl = st.run(*model, list(lefts))
    _, fr = st.run(*model, list(rights))
    fl = fl / np.linalg.norm(fl, axis=1, keepdims=True)
    fr = fr / np.linalg.norm(fr, axis=1, keepdims=True)
    return 1 - (fl * fr).sum(1)


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt"))
    args = ap.parse_args()
    model = st.load_model(Path(args.checkpoint))
    out = {}
    feats = {}
    for split, root in [("validation", DATA / "case_split_fixed" / "val"), ("test", DATA / "kaggle_split_fixed" / "test")]:
        ims, y = labelled(root)
        p, _ = st.run(*model, ims)
        a = asymmetry(model, ims)
        feats[split] = (np.c_[p, a], y)
        out[split] = {
            "photos": int(len(y)),
            "auc_asymmetry_alone": float(roc_auc_score(y, a)),
            "auc_model_alone": float(roc_auc_score(y, p)),
            "asymmetry_median_noncancer": float(np.median(a[~y])),
            "asymmetry_median_cancer": float(np.median(a[y])),
            "asymmetry_p90_noncancer": float(np.percentile(a[~y], 90)),
        }
    clf = LogisticRegression().fit(*feats["validation"])
    xt, yt = feats["test"]
    out["test"]["auc_model_plus_asymmetry"] = float(roc_auc_score(yt, clf.predict_proba(xt)[:, 1]))
    out["combined_coefficients"] = {"p_cancer": float(clf.coef_[0][0]), "asymmetry": float(clf.coef_[0][1])}
    print(json.dumps(out, indent=2))
    (ML_DIR / "artifacts" / "asymmetry_experiment.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
