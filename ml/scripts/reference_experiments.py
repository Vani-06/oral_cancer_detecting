"""
Experiments for same-patient reference assessment (local branch only; not
for public release before a patent filing).

A. Stability-based three-way output. Each photo is re-scored under a fixed
   set of diagnosis-preserving edits. The share of edits voting Cancer
   decides: Cancer (>= HI), No cancer (<= LO), otherwise Inconclusive
   ("retake / refer"). LO and HI are chosen on the VALIDATION split only
   (smallest inconclusive rate that keeps decided-case accuracy at or above
   a target), then applied once to the test split and the external photos.

B. Reference colour normalisation, simulated. Real paired photos (lesion +
   same patient's opposite side) do not exist yet, so: apply one random
   acquisition shift (colour cast, white balance, exposure) to a photo AND
   to a healthy "reference" photo -- the same camera and light -- then
   re-express the photo in population-normal colour using the reference:
       x_norm = (x - mean_ref) / std_ref * std_pop + mean_pop   (per channel, Lab)
   where mean_pop / std_pop come from healthy training photos. The
   reference is a DIFFERENT person's healthy mouth, so this underestimates
   what a true same-patient reference can do.

Usage:
    .venv/Scripts/python.exe scripts/reference_experiments.py [--checkpoint artifacts/resnet50_oral_cancer_v7.pt]
"""

import argparse
import csv
import io
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageEnhance, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
EXTS = st.IMAGE_EXTS


def _jpeg(im, q):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _crop(im, frac):
    w, h = im.size
    dw, dh = int(w * (1 - frac) / 2), int(h * (1 - frac) / 2)
    return im.crop((dw, dh, w - dw, h - dh))


# Must match backend/app/services/inference_service.py STABILITY_EDITS.
STABILITY_EDITS = [
    lambda im: im,
    ImageOps.mirror,
    lambda im: im.rotate(90, expand=True),
    lambda im: im.rotate(180),
    lambda im: im.rotate(270, expand=True),
    lambda im: ImageEnhance.Brightness(im).enhance(0.85),
    lambda im: ImageEnhance.Brightness(im).enhance(1.15),
    lambda im: _jpeg(im, 40),
    lambda im: _crop(im, 0.85),
]

_SRGB = ImageCms.createProfile("sRGB")
_LAB = ImageCms.createProfile("LAB")
TO_LAB = ImageCms.buildTransformFromOpenProfiles(_SRGB, _LAB, "RGB", "LAB")
TO_RGB = ImageCms.buildTransformFromOpenProfiles(_LAB, _SRGB, "LAB", "RGB")


def lab_stats(im):
    a = np.asarray(ImageCms.applyTransform(im, TO_LAB), dtype=np.float32).reshape(-1, 3)
    return a.mean(0), a.std(0) + 1e-3


def normalise_with_reference(im, ref_stats, pop_stats):
    (mr, sr), (mp, sp) = ref_stats, pop_stats
    lab = np.asarray(ImageCms.applyTransform(im, TO_LAB), dtype=np.float32)
    out = np.clip((lab - mr) / sr * sp + mp, 0, 255).astype(np.uint8)
    return ImageCms.applyTransform(Image.fromarray(out, "LAB"), TO_RGB)


def acquisition_shift(rng):
    """One camera / light condition, applied identically to photo and reference."""
    cast = rng.uniform(0.8, 1.25, 3)
    bright = rng.uniform(0.65, 1.35)
    sat = rng.uniform(0.6, 1.5)

    def apply(im):
        a = np.asarray(im, dtype=np.float32) * cast
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        im = ImageEnhance.Brightness(im).enhance(bright)
        return ImageEnhance.Color(im).enhance(sat)
    return apply


def labelled(root):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in EXTS)
    return [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def votes(model, images):
    """Share of stability edits voting Cancer, per image."""
    return np.mean([st.run(*model, [e(im) for im in images])[0] >= 0.5 for e in STABILITY_EDITS], 0)


def three_way(v, lo, hi):
    return np.where(v >= hi, 1, np.where(v <= lo, 0, -1))  # -1 = inconclusive


def choose_thresholds(v, y, target=0.92):
    best = None
    grid = np.round(np.arange(0, 1.0001, 1 / len(STABILITY_EDITS)), 4)
    for lo in grid:
        for hi in grid:
            if hi <= lo:
                continue
            d = three_way(v, lo, hi)
            decided = d >= 0
            if decided.mean() == 0:
                continue
            acc = (d[decided] == y[decided]).mean()
            cand = (acc >= target, decided.mean(), acc, lo, hi)
            if best is None or cand > best:
                best = cand
    _, _, _, lo, hi = best
    return float(lo), float(hi)


def report(name, v, y, lo, hi):
    d = three_way(v, lo, hi)
    dec = d >= 0
    out = {
        "photos": int(len(y)),
        "inconclusive": float((~dec).mean()),
        "decided_accuracy": float((d[dec] == y[dec]).mean()) if dec.any() else None,
        "single_answer_accuracy": float(((v >= 0.5) == y).mean()),
    }
    if y.any():
        out["cancers_called_cancer"] = float((d[y] == 1).mean())
        out["cancers_called_no_cancer"] = float((d[y] == 0).mean())
    if (~y).any():
        out["noncancer_called_cancer"] = float((d[~y] == 1).mean())
        out["noncancer_called_no_cancer"] = float((d[~y] == 0).mean())
    print(f"  {name:28s} " + "  ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in out.items()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt"))
    ap.add_argument("--target", type=float, default=0.92, help="decided-case accuracy to keep on validation")
    args = ap.parse_args()
    model = st.load_model(Path(args.checkpoint))
    results = {}

    val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    hold = [st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
            for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv"))]
    ext = DATA / "external" / "olp_synthesis" / "extracted" / "data"
    cheek = [st.open_rgb(p) for p in sorted((ext / "negative").glob("*"))]
    olp = [st.open_rgb(p) for p in sorted((ext / "lesion_img").glob("*"))]

    print("A. stability-based three-way output")
    vv = votes(model, val_im)
    lo, hi = choose_thresholds(vv, val_y, args.target)
    print(f"  thresholds chosen on validation: no cancer if <= {lo:.3f} of edits vote Cancer, cancer if >= {hi:.3f}")
    results["thresholds"] = {"lo": lo, "hi": hi, "edits": len(STABILITY_EDITS), "target": args.target}
    results["validation"] = report("validation (chosen here)", vv, val_y, lo, hi)
    results["test"] = report("Kaggle test (corrected)", votes(model, test_im), test_y, lo, hi)
    results["client_holdout"] = report("client dysplasia, no cancer", votes(model, hold), np.zeros(len(hold), bool), lo, hi)
    results["external_cheek"] = report("external healthy cheek", votes(model, cheek), np.zeros(len(cheek), bool), lo, hi)
    results["external_olp"] = report("external lichen planus", votes(model, olp), np.zeros(len(olp), bool), lo, hi)

    print("\nB. reference colour normalisation under a shared camera/light shift (simulated)")
    train_healthy = [st.open_rgb(p) for p in sorted((DATA / "case_split_fixed" / "train" / "Non-Cancer").glob("*"))]
    stats = [lab_stats(im) for im in train_healthy]
    pop = (np.mean([s[0] for s in stats], 0), np.mean([s[1] for s in stats], 0))
    refs = [im for im, y in zip(val_im, val_y) if not y]
    sim = {}
    for split, ims, ys in [("validation", val_im, val_y), ("test", test_im, test_y)]:
        rng = np.random.default_rng(0)
        rr = random.Random(0)
        shifted, normed, plain_normed = [], [], []
        for im in ims:
            shift = acquisition_shift(rng)
            ref = shift(rr.choice(refs))
            target = shift(im)
            shifted.append(target)
            normed.append(normalise_with_reference(target, lab_stats(ref), pop))
            plain_normed.append(normalise_with_reference(target, lab_stats(target), pop))
        p0 = st.run(*model, ims)[0] >= 0.5
        p1 = st.run(*model, shifted)[0] >= 0.5
        p2 = st.run(*model, normed)[0] >= 0.5
        p3 = st.run(*model, plain_normed)[0] >= 0.5
        row = {f: float(((p == ys).mean())) for f, p in
               [("original", p0), ("shifted", p1), ("shifted_reference_normalised", p2), ("shifted_self_normalised", p3)]}
        row["answers_changed_by_shift"] = float((p1 != p0).mean())
        row["answers_changed_after_reference_normalisation"] = float((p2 != p0).mean())
        sim[split] = row
        print(f"  {split:10s} accuracy: original {row['original']:.3f} | shifted {row['shifted']:.3f} | "
              f"+ reference normalisation {row['shifted_reference_normalised']:.3f} | "
              f"+ photo's own statistics {row['shifted_self_normalised']:.3f} | answers changed by shift "
              f"{row['answers_changed_by_shift']:.3f} -> {row['answers_changed_after_reference_normalisation']:.3f}")
    results["reference_normalisation_simulation"] = sim
    results["population_lab_stats"] = {"mean": pop[0].tolist(), "std": pop[1].tolist()}
    (ML_DIR / "artifacts" / "reference_experiments.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
