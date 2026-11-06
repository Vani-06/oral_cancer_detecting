"""
Risk-controlled triage with a statistical guarantee (CONFIDENTIAL).

Score per photo: mean P(cancer) over the 9 diagnosis-preserving edits
(the acquisition-consensus score). Three outcomes:
    score <  lam_lo           -> "no cancer"
    score >= lam_hi           -> "cancer"
    otherwise                 -> "inconclusive: refer"

lam_lo is set on the validation (calibration) split by
  * conformal risk control (Angelopoulos et al. 2022): the largest lam with
    (n * FNR_cal(lam) + 1) / (n + 1) <= alpha, which bounds the EXPECTED
    share of cancers called "no cancer" by alpha; and
  * a high-probability version (Learn-then-Test style): the largest lam whose
    one-sided Clopper-Pearson upper bound on FNR at confidence 1-delta is
    <= alpha.
lam_hi is the smallest threshold keeping non-cancers called "cancer" at or
below beta on validation.

The guarantee assumes calibration and test photos are exchangeable; here
validation mixes Kaggle and client photos and test is Kaggle only, so the
test check is an honest stress of that assumption, not a formality.

Usage:
    .venv/Scripts/python.exe scripts/conformal_triage.py [--alpha 0.05 --delta 0.1 --beta 0.10]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import beta as beta_dist

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402
from reference_experiments import STABILITY_EDITS  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"


def apply_temperature(p, t):
    """Binary softmax(z / t) from p = softmax(z): sigmoid(logit(p) / t)."""
    if t == 1.0:
        return p
    logit = np.log(np.clip(p, 1e-7, 1 - 1e-7) / np.clip(1 - p, 1e-7, 1))
    return 1 / (1 + np.exp(-logit / t))


def consensus_scores(model, images, temperature=1.0):
    """Mean calibrated P(cancer) over the 9 edits -- what the app computes."""
    return np.mean([apply_temperature(st.run(*model, [e(im) for im in images])[0], temperature)
                    for e in STABILITY_EDITS], 0)


def clopper_pearson_upper(k, n, delta):
    return 1.0 if k >= n else float(beta_dist.ppf(1 - delta, k + 1, n - k))


def lam_lo_crc(s_cancer, alpha):
    n = len(s_cancer)
    best = 0.0
    for lam in np.unique(np.r_[0.0, s_cancer]):
        fnr = (s_cancer < lam).mean()
        if (n * fnr + 1) / (n + 1) <= alpha:
            best = max(best, lam)
    return float(best)


def lam_lo_hp(s_cancer, alpha, delta):
    n = len(s_cancer)
    best = 0.0
    for lam in np.sort(np.unique(np.r_[0.0, s_cancer])):
        if clopper_pearson_upper(int((s_cancer < lam).sum()), n, delta) <= alpha:
            best = lam
        else:
            break  # FNR only grows with lam
    return float(best)


def lam_hi_for(s_noncancer, beta):
    for lam in np.sort(np.unique(s_noncancer)):
        if (s_noncancer >= lam).mean() <= beta:
            return float(lam)
    return 1.0


def outcome(s, lo, hi):
    return np.where(s >= hi, 1, np.where(s < lo, 0, -1))


def summarise(s, y, lo, hi):
    d = outcome(s, lo, hi)
    return {
        "cancers_called_no_cancer": float((d[y] == 0).mean()),
        "referral_sensitivity": float((d[y] != 0).mean()),
        "noncancer_cleared": float((d[~y] == 0).mean()),
        "noncancer_called_cancer": float((d[~y] == 1).mean()),
        "inconclusive": float((d == -1).mean()),
    }


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt"))
    ap.add_argument("--alpha", type=float, default=0.05, help="target share of cancers called 'no cancer'")
    ap.add_argument("--delta", type=float, default=0.10, help="1 - confidence for the high-probability version")
    ap.add_argument("--beta", type=float, default=0.10, help="max share of non-cancers called 'cancer'")
    ap.add_argument("--temperature", type=float, default=1.0, help="the app's TEMPERATURE setting")
    ap.add_argument("--out", default="conformal_triage.json", help="file name under artifacts/")
    args = ap.parse_args()
    model = st.load_model(Path(args.checkpoint))
    val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    sv = consensus_scores(model, val_im, args.temperature)
    stt = consensus_scores(model, test_im, args.temperature)
    hi = lam_hi_for(sv[~val_y], args.beta)
    out = {"checkpoint": Path(args.checkpoint).name, "temperature": args.temperature,
           "alpha": args.alpha, "delta": args.delta, "beta": args.beta, "lam_hi": hi,
           "calibration_cancers": int(val_y.sum()), "test_cancers": int(test_y.sum())}
    for name, lo in [("expected_guarantee_CRC", lam_lo_crc(sv[val_y], args.alpha)),
                     ("high_probability_guarantee", lam_lo_hp(sv[val_y], args.alpha, args.delta))]:
        out[name] = {"lam_lo": lo, "validation": summarise(sv, val_y, lo, hi), "test": summarise(stt, test_y, lo, hi)}
    # Smallest alpha the high-probability version can certify with this many calibration cancers.
    out["min_certifiable_alpha_at_delta"] = clopper_pearson_upper(0, int(val_y.sum()), args.delta)
    print(json.dumps(out, indent=2))
    (ML_DIR / "artifacts" / args.out).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
