"""
Single-photo self-referenced lesion analysis (CONFIDENTIAL; private branch).

The cancer model's class activation map (CAM, exact for ResNet's global-
average-pool + linear head) locates the most cancer-like region of the
photo. Instead of judging the photo as a whole, compare that region with the
patient's own surrounding tissue in the SAME photo -- same camera, light,
pigmentation and staining:

    A        = normalised CAM over the 7x7 layer4 feature map
    f_lesion = A-weighted mean of layer4 features
    f_around = (1-A)-weighted mean of layer4 features
    contrast = 1 - cos(f_lesion, f_around)

Features (all low-dimensional): logit P(cancer), contrast, lesion-vs-around
cancer-logit difference, CAM peakedness, attended area. A logistic head is
fitted on the VALIDATION split only (few parameters, like a threshold) and
compared with the model's own score on the corrected TEST split and the
external sets, at the same sensitivity (operating points fixed on validation).

Usage:
    .venv/Scripts/python.exe scripts/self_reference_experiment.py [--checkpoint artifacts/resnet50_oral_cancer_v7.pt]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
FEATURES = ["logit_p", "contrast", "logit_gap", "cam_peak", "cam_area"]


@torch.no_grad()
def describe(model_bundle, images):
    model, tf, cancer_idx = model_bundle
    w = model.fc.weight[cancer_idx] - model.fc.weight[1 - cancer_idx]  # cancer-vs-other direction
    b = model.fc.bias[cancer_idx] - model.fc.bias[1 - cancer_idx]
    maps = []
    hook = model.layer4.register_forward_hook(lambda m, i, o: maps.append(o))
    rows = []
    try:
        for start in range(0, len(images), 16):
            maps.clear()
            batch = torch.stack([tf(im) for im in images[start:start + 16]])
            logits = model(batch)
            fmap = maps[0]  # B x 2048 x 7 x 7
            cam = torch.einsum("c,bchw->bhw", w, fmap)
            a = torch.relu(cam)
            a = a / (a.flatten(1).max(1).values[:, None, None] + 1e-8)
            pooled = lambda wt: (fmap * wt[:, None]).flatten(2).sum(2) / (wt.flatten(1).sum(1)[:, None] + 1e-8)  # noqa: E731
            f_les, f_aro = pooled(a), pooled(1 - a)
            contrast = 1 - torch.nn.functional.cosine_similarity(f_les, f_aro, dim=1)
            gap = (f_les - f_aro) @ w
            p = torch.softmax(logits, 1)[:, cancer_idx].clamp(1e-6, 1 - 1e-6)
            for i in range(len(batch)):
                rows.append([float(torch.log(p[i] / (1 - p[i]))), float(contrast[i]), float(gap[i]),
                             float(a[i].max() - a[i].mean()), float((a[i] > 0.5).float().mean())])
    finally:
        hook.remove()
    return np.array(rows)


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def threshold_for_sensitivity(score, y, sens):
    """Highest threshold that keeps at least `sens` of cancers above it."""
    cs = np.sort(score[y])[::-1]
    k = int(np.ceil(sens * len(cs))) - 1
    return cs[max(k, 0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt"))
    args = ap.parse_args()
    bundle = st.load_model(Path(args.checkpoint))

    val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    hold = [st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
            for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv"))]
    ext = DATA / "external" / "olp_synthesis" / "extracted" / "data"
    cheek = [st.open_rgb(p) for p in sorted((ext / "negative").glob("*"))]
    olp = [st.open_rgb(p) for p in sorted((ext / "lesion_img").glob("*"))]
    zoomed = [st.center_crop(im, 0.4) for im, y in zip(test_im, test_y) if not y]

    X = {k: describe(bundle, ims) for k, ims in
         [("val", val_im), ("test", test_im), ("hold", hold), ("cheek", cheek), ("olp", olp), ("zoom", zoomed)]}

    scaler = StandardScaler().fit(X["val"])
    head = LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000).fit(scaler.transform(X["val"]), val_y)
    new = {k: head.decision_function(scaler.transform(v)) for k, v in X.items()}
    old = {k: v[:, 0] for k, v in X.items()}  # the model's own logit

    out = {"coefficients": dict(zip(FEATURES, map(float, head.coef_[0]))),
           "auc": {"validation_model": float(roc_auc_score(val_y, old["val"])),
                   "test_model": float(roc_auc_score(test_y, old["test"])),
                   "test_self_reference": float(roc_auc_score(test_y, new["test"])),
                   "test_contrast_alone": float(roc_auc_score(test_y, X["test"][:, 1]))}}
    print("coefficients:", {k: round(v, 2) for k, v in out["coefficients"].items()})
    print("AUC  model alone: val %.3f test %.3f | self-reference: test %.3f | lesion-vs-surround contrast alone: test %.3f" % (
        out["auc"]["validation_model"], out["auc"]["test_model"], out["auc"]["test_self_reference"], out["auc"]["test_contrast_alone"]))

    out["operating_points"] = {}
    for sens in (0.85, 0.90, 0.95):
        row = {}
        for name, s in [("model", old), ("self_reference", new)]:
            t = threshold_for_sensitivity(s["val"], val_y, sens)  # fixed on validation
            flag = {k: v >= t for k, v in s.items()}
            row[name] = {
                "test_sensitivity": float(flag["test"][test_y].mean()),
                "test_specificity": float((~flag["test"][~test_y]).mean()),
                "client_dysplasia_flagged": float(flag["hold"].mean()),
                "healthy_zoomed_flagged": float(flag["zoom"].mean()),
                "external_healthy_cheek_flagged": f"{int(flag['cheek'].sum())}/{len(cheek)}",
                "external_lichen_planus_flagged": f"{int(flag['olp'].sum())}/{len(olp)}",
            }
        out["operating_points"][f"val_sensitivity_{sens}"] = row
        print(f"\n-- operating point: {sens:.0%} of validation cancers caught")
        for name, r in row.items():
            print(f"   {name:15s} test sens {r['test_sensitivity']:.3f} spec {r['test_specificity']:.3f} | client dysplasia flagged "
                  f"{r['client_dysplasia_flagged']:.3f} | zoomed healthy {r['healthy_zoomed_flagged']:.3f} | "
                  f"healthy cheek {r['external_healthy_cheek_flagged']} | lichen planus {r['external_lichen_planus_flagged']}")
    (ML_DIR / "artifacts" / "self_reference_experiment.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
