"""
Score cancer checkpoints side by side on every held-out set we have, using
the corrected labels from scripts/fix_labels.py.

- validation (case_split_fixed/val): the only set used to choose a model
- Kaggle test (kaggle_split_fixed/test): cancers caught, healthy flagged
- client held-out dysplasia patients (never cancer): flagged
- Kaggle test healthy photos zoomed to 40%: the close-up shortcut
- external, never used anywhere: healthy cheek mucosa and oral lichen planus
  photos from Mendeley fgjd95tcr8 (CC BY 4.0)

Usage:
    .venv/Scripts/python.exe scripts/compare_models.py v4 v7 [...]
"""

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def main():
    val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    holdout = [st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
               for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv"))]
    zoomed = [st.center_crop(im, 0.4) for im, y in zip(test_im, test_y) if not y]
    ext = DATA / "external" / "olp_synthesis" / "extracted" / "data"
    cheek = [st.open_rgb(p) for p in sorted((ext / "negative").glob("*"))]
    olp = [st.open_rgb(p) for p in sorted((ext / "lesion_img").glob("*"))]

    print(f"{'model':6s} | {'VALIDATION caught / false':>26s} | {'TEST caught':>13s} {'healthy flagged':>16s} | "
          f"{'client flagged':>14s} | {'zoomed healthy':>14s} | {'healthy cheek':>13s} {'lichen planus':>13s}")
    for name in sys.argv[1:]:
        model = st.load_model(ML_DIR / "artifacts" / f"resnet50_oral_cancer_{name}.pt")
        call = lambda ims: st.run(*model, ims)[0] >= 0.5  # noqa: E731
        v, t = call(val_im), call(test_im)
        h, z, c, o = call(holdout), call(zoomed), call(cheek), call(olp)
        print(f"{name:6s} | {v[val_y].mean():12.1%} / {v[~val_y].mean():6.1%}     | "
              f"{t[test_y].mean():6.1%} ({t[test_y].sum()}/{test_y.sum()}) {t[~test_y].mean():9.1%} ({t[~test_y].sum()}/{(~test_y).sum()}) | "
              f"{h.mean():6.1%} ({h.sum()}/{len(h)}) | {z.mean():6.1%} ({z.sum()}/{len(z)}) | "
              f"{c.sum()}/{len(c)} flagged    {o.sum()}/{len(o)} flagged", flush=True)


if __name__ == "__main__":
    main()
