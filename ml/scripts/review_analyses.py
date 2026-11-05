"""
Analyses requested by the external review (items 1, 2, 8, 9, 24, 25, 27,
29, 32 and the untouched final test set for item 17).

Calibration/selection: validation split only (case_split_fixed/val).
Reported: corrected Kaggle test (seen during development, so partly tuned),
and -- with --final, once -- the untouched set built by build_fresh_test.py.

Usage:
    .venv/Scripts/python.exe scripts/review_analyses.py            # development sets
    .venv/Scripts/python.exe scripts/review_analyses.py --final    # adds the untouched set
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from scipy.stats import beta as beta_dist
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402
from conformal_triage import lam_hi_for, lam_lo_crc  # noqa: E402
from reference_experiments import STABILITY_EDITS  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
PREVALENCES = [0.01, 0.02, 0.05, 0.20]


def cp(k, n):
    lo = 0.0 if k == 0 else float(beta_dist.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(beta_dist.ppf(0.975, k + 1, n - k))
    return {"k": int(k), "n": int(n), "rate": float(k / n) if n else None, "ci95": [lo, hi]}


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return paths, [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def scores(model, ims):
    single = st.run(*model, ims)[0]
    consensus = np.mean([st.run(*model, [e(im) for im in ims])[0] for e in STABILITY_EDITS], 0)
    return single, consensus


def three_way(s, lo, hi):
    return np.where(s >= hi, "cancer", np.where(s < lo, "no_cancer", "inconclusive"))


def confusion(out, y):
    rows = {}
    for name, mask in [("cancers", y), ("non_cancers", ~y)]:
        n = int(mask.sum())
        rows[name] = {k: cp(int((out[mask] == k).sum()), n) for k in ("cancer", "inconclusive", "no_cancer")}
    return rows


def at_prevalence(sens, spec):
    out = {}
    for prev in PREVALENCES:
        ppv = sens * prev / (sens * prev + (1 - spec) * (1 - prev))
        npv = spec * (1 - prev) / (spec * (1 - prev) + (1 - sens) * prev)
        flagged = 1000 * (sens * prev + (1 - spec) * (1 - prev))
        out[f"{prev:.0%}"] = {"ppv": ppv, "npv": npv, "flagged_per_1000": flagged,
                              "true_cancers_among_flagged_per_1000": 1000 * sens * prev,
                              "missed_cancers_per_1000": 1000 * (1 - sens) * prev}
    return out


def ece(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    return float(sum(((p >= a) & (p < b if b < 1 else p <= b)).mean() *
                     abs(p[(p >= a) & (p < b if b < 1 else p <= b)].mean() - y[(p >= a) & (p < b if b < 1 else p <= b)].mean())
                     for a, b in zip(edges[:-1], edges[1:]) if ((p >= a) & (p < b if b < 1 else p <= b)).any()))


def temperature(p_val, y_val):
    logit = np.log(np.clip(p_val, 1e-6, 1 - 1e-6) / np.clip(1 - p_val, 1e-6, 1))
    best = min(np.linspace(0.3, 5, 200), key=lambda t: -np.mean(
        y_val * np.log(1 / (1 + np.exp(-logit / t)) + 1e-9) + (1 - y_val) * np.log(1 - 1 / (1 + np.exp(-logit / t)) + 1e-9)))
    return float(best)


def apply_t(p, t):
    logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    return 1 / (1 + np.exp(-logit / t))


@torch.no_grad()
def imagenet_features(images):
    m = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2).eval()
    m.fc = torch.nn.Identity()
    tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    out = [m(torch.stack([tf(im) for im in images[i:i + 32]])) for i in range(0, len(images), 32)]
    f = torch.cat(out).numpy()
    return f / np.linalg.norm(f, axis=1, keepdims=True)


@torch.no_grad()
def grade_none_on_cancer_calls(images, cancer_call):
    """How often the 'cancer is never paired with no dysplasia' rule fires."""
    ck = torch.load(ML_DIR / "artifacts" / "resnet50_dysplasia_grade_v2.pt", map_location="cpu", weights_only=False)
    m = resnet50(weights=None)
    m.fc = torch.nn.Linear(2048, len(ck["class_to_idx"]))
    m.load_state_dict(ck["state_dict"])
    m.eval()
    tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(), transforms.Normalize(ck["mean"], ck["std"])])
    none = ck["class_to_idx"]["no_dysplasia"]
    sel = [im for im, c in zip(images, cancer_call) if c]
    if not sel:
        return cp(0, 0)
    pred = torch.cat([m(torch.stack([tf(im) for im in sel[i:i + 32]])).argmax(1) for i in range(0, len(sel), 32)])
    return cp(int((pred == none).sum()), len(sel))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="also evaluate the untouched set (do this once)")
    args = ap.parse_args()
    model = st.load_model(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt")
    out = {}

    _, val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    test_paths, test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    vs, vc = scores(model, val_im)
    ts, tc = scores(model, test_im)

    # Item 8: ablation -- same conformal calibration on single-pass vs consensus score.
    thr = {}
    for name, v, t in [("single_pass", vs, ts), ("consensus_9_edits", vc, tc)]:
        lo, hi = lam_lo_crc(v[val_y], 0.05), lam_hi_for(v[~val_y], 0.10)
        thr[name] = (lo, hi)
        o = three_way(t, lo, hi)
        out.setdefault("ablation_test", {})[name] = {"lam_lo": lo, "lam_hi": hi, "confusion": confusion(o, test_y),
                                                      "validation_noncancer_called_cancer": float((v[~val_y] >= hi).mean())}
    # Item 27/24: full per-class table for the model in use (consensus) on test.
    lo, hi = thr["consensus_9_edits"]
    test_out = three_way(tc, lo, hi)
    out["triage_test_confusion"] = confusion(test_out, test_y)

    # Items 1/2: prevalence-adjusted figures.
    single_sens, single_spec = float((ts[test_y] >= 0.5).mean()), float((ts[~test_y] < 0.5).mean())
    refer = test_out != "no_cancer"
    refer_sens, refer_spec = float(refer[test_y].mean()), float((~refer[~test_y]).mean())
    out["prevalence"] = {"single_answer": at_prevalence(single_sens, single_spec),
                         "triage_refer_if_cancer_or_inconclusive": at_prevalence(refer_sens, refer_spec)}

    # Item 9: simple baseline on the identical split.
    tr_paths, tr_im, tr_y = labelled(DATA / "case_split_fixed" / "train")
    clf = LogisticRegression(C=1.0, max_iter=3000).fit(imagenet_features(tr_im), tr_y)
    pb = clf.predict_proba(imagenet_features(test_im))[:, 1]
    out["baseline_frozen_imagenet_lr_test"] = {
        "auc": float(roc_auc_score(test_y, pb)), "sensitivity": float((pb[test_y] >= 0.5).mean()),
        "specificity": float((pb[~test_y] < 0.5).mean())}
    out["round7_test"] = {"auc": float(roc_auc_score(test_y, ts)), "sensitivity": single_sens, "specificity": single_spec}

    # Item 29: temperature scaling fitted on validation.
    t = temperature(vs, val_y.astype(float))
    out["calibration"] = {"temperature": t, "test_ece_before": ece(ts, test_y), "test_ece_after": ece(apply_t(ts, t), test_y),
                          "test_brier_before": float(np.mean((ts - test_y) ** 2)),
                          "test_brier_after": float(np.mean((apply_t(ts, t) - test_y) ** 2))}

    # Item 32: specificity by type of non-cancer (single answer and triage).
    benign_mask = np.array([p.name.startswith("relabelled_") for p in test_paths])
    hold = [st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
            for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv"))]
    ext = DATA / "external" / "olp_synthesis" / "extracted" / "data"
    groups = {
        "kaggle_normal_or_other": [im for im, y, b in zip(test_im, test_y, benign_mask) if not y and not b],
        "kaggle_benign_lesions": [im for im, b in zip(test_im, benign_mask) if b],
        "client_dysplasia_heldout": hold,
        "external_healthy_cheek": [st.open_rgb(p) for p in sorted((ext / "negative").glob("*"))],
        "external_lichen_planus": [st.open_rgb(p) for p in sorted((ext / "lesion_img").glob("*"))],
    }
    out["by_noncancer_type"] = {}
    for name, ims in groups.items():
        s1, sc = scores(model, ims)
        o = three_way(sc, lo, hi)
        out["by_noncancer_type"][name] = {
            "single_answer_flagged": cp(int((s1 >= 0.5).sum()), len(ims)),
            "triage_cancer": cp(int((o == "cancer").sum()), len(ims)),
            "triage_inconclusive": cp(int((o == "inconclusive").sum()), len(ims)),
            "triage_cleared": cp(int((o == "no_cancer").sum()), len(ims))}

    # Item 25: the grade override.
    out["grade_rule_fires_on_test_cancer_calls"] = grade_none_on_cancer_calls(test_im, ts >= 0.5)

    if args.final:
        _, f_im, f_y = labelled(DATA / "fresh_test")
        fs, fc = scores(model, f_im)
        fo = three_way(fc, lo, hi)
        out["untouched_final_test"] = {
            "photos": int(len(f_y)), "cancers": int(f_y.sum()),
            "single_answer": {"auc": float(roc_auc_score(f_y, fs)),
                              "sensitivity": cp(int((fs[f_y] >= 0.5).sum()), int(f_y.sum())),
                              "specificity": cp(int((fs[~f_y] < 0.5).sum()), int((~f_y).sum()))},
            "triage_confusion": confusion(fo, f_y)}

    path = ML_DIR / "artifacts" / ("review_analyses_final.json" if args.final else "review_analyses.json")
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
