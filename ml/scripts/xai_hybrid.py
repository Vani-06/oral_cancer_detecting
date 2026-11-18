"""
Explanation-guided cascaded hybrid (XAI-guided global-local fusion).

  Stage 1  global ResNet-50 (resnet50_oral_cancer_v7) scores the whole photo
  Stage 2  Grad-CAM of stage 1 (cancer class) locates the region that drove
           the score; that region is cropped and enlarged
  Stage 3  a second ResNet-50, trained only on such crops, scores the close-up
  Stage 4  the two probabilities are fused: p = w * p_global + (1 - w) * p_local,
           with w chosen on the validation split
  Stage 5  conformal risk control turns the fused score into cancer /
           inconclusive / no cancer (thresholds set on validation)

Usage (from ml/):
  python scripts/xai_hybrid.py crops            # writes data/xai_crops/... for training stage 3
  python scripts/train.py --train-dir data/xai_crops/train --val-dir data/xai_crops/val \
      --checkpoint-name resnet50_oral_cancer_local_v1.pt
  python scripts/xai_hybrid.py eval             # all comparisons, artifacts/xai_hybrid.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402
from conformal_triage import lam_hi_for, lam_lo_crc  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
ART = ML_DIR / "artifacts"
GLOBAL_CKPT = ART / "resnet50_oral_cancer_v7.pt"
LOCAL_CKPT = ART / "resnet50_oral_cancer_local_v1.pt"
CROPS = DATA / "xai_crops"

CAM_THRESHOLD = 0.5  # fraction of the map's peak that counts as "attended"
MARGIN = 0.15  # context added around the attended box, as a fraction of its size
MIN_SIDE = 0.25  # smallest crop side, as a fraction of the photo's shorter side


def grad_cam(model, tf, cancer_idx, image: Image.Image) -> np.ndarray:
    """Grad-CAM for the cancer class on layer4, normalised to [0, 1], 7 x 7."""
    acts, grads = {}, {}
    fh = model.layer4.register_forward_hook(lambda m, i, o: acts.update(v=o))
    bh = model.layer4.register_full_backward_hook(lambda m, gi, go: grads.update(v=go[0]))
    try:
        out = model(tf(image).unsqueeze(0))
        model.zero_grad()
        out[0, cancer_idx].backward()
        weights = grads["v"][0].mean(dim=(1, 2))
        cam = torch.relu((weights[:, None, None] * acts["v"][0]).sum(0)).detach().numpy()
    finally:
        fh.remove()
        bh.remove()
    return cam / cam.max() if cam.max() > 0 else cam


def attended_box(cam: np.ndarray, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Bounding box (in photo pixels) of the attended region, with margin."""
    w, h = size
    cam_up = np.asarray(Image.fromarray(np.uint8(255 * cam)).resize((w, h), Image.BILINEAR)) / 255.0
    ys, xs = np.nonzero(cam_up >= CAM_THRESHOLD)
    if len(xs) == 0:  # no attention at all: fall back to a centre crop
        x0, y0, x1, y1 = 0.2 * w, 0.2 * h, 0.8 * w, 0.8 * h
    else:
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw, bh = x1 - x0, y1 - y0
    side = max(bw, bh) * (1 + 2 * MARGIN)
    side = max(side, MIN_SIDE * min(w, h))
    side = min(side, min(w, h))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left = int(np.clip(cx - side / 2, 0, w - side))
    top = int(np.clip(cy - side / 2, 0, h - side))
    return left, top, left + int(side), top + int(side)


def xai_crop(model, tf, cancer_idx, image: Image.Image) -> tuple[Image.Image, float]:
    """The attended close-up and the share of the photo it covers."""
    box = attended_box(grad_cam(model, tf, cancer_idx, image), image.size)
    area = (box[2] - box[0]) * (box[3] - box[1]) / (image.size[0] * image.size[1])
    return image.crop(box), float(area)


def labelled(root: Path):
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    return paths, [st.open_rgb(p) for p in paths], np.array([p.parent.name == "Cancer" for p in paths])


def cmd_crops() -> None:
    model = st.load_model(GLOBAL_CKPT)
    for split in ("train", "val"):
        paths, images, _ = labelled(DATA / "case_split_fixed" / split)
        areas = []
        for path, image in zip(paths, images, strict=True):
            crop, area = xai_crop(*model, image)
            out = CROPS / split / path.parent.name / path.name
            out.parent.mkdir(parents=True, exist_ok=True)
            crop.convert("RGB").save(out.with_suffix(".jpg"), quality=95)
            areas.append(area)
        print(f"{split}: {len(paths)} crops, median crop covers {np.median(areas):.0%} of the photo", flush=True)


# --- evaluation ---


def scores(global_model, local_model, images):
    """(p_global, p_local) for each photo; the crop comes from the global model's Grad-CAM."""
    p_global = st.run(*global_model, images)[0]
    crops = [xai_crop(*global_model, im)[0] for im in images]
    p_local = st.run(*local_model, crops)[0]
    return p_global, p_local


def threshold_metrics(p, y):
    call = p >= 0.5
    return {"sensitivity": float(call[y].mean()), "specificity": float((~call[~y]).mean())}


def auc_ci_diff(y, a, b, n=2000, seed=0):
    """Paired bootstrap of AUC(a) - AUC(b): mean difference and 95% interval."""
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].all() or (~y[i]).all():
            continue
        diffs.append(roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]))
    return {
        "mean": float(np.mean(diffs)),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
    }


def triage(p, y, lo, hi):
    out = np.where(p >= hi, "cancer", np.where(p < lo, "no_cancer", "inconclusive"))
    return {
        "cancers_called_no_cancer": f"{int((out[y] == 'no_cancer').sum())}/{int(y.sum())}",
        "cancers_inconclusive": f"{int((out[y] == 'inconclusive').sum())}/{int(y.sum())}",
        "noncancer_cleared": f"{int((out[~y] == 'no_cancer').sum())}/{int((~y).sum())}",
        "noncancer_called_cancer": f"{int((out[~y] == 'cancer').sum())}/{int((~y).sum())}",
    }


def zoomed_out(im: Image.Image) -> Image.Image:
    """The photo shrunk to 45% and placed on a grey border (lesion small in frame)."""
    w, h = im.size
    canvas = Image.new("RGB", (w, h), (120, 110, 105))
    small = im.resize((int(w * 0.45), int(h * 0.45)))
    canvas.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
    return canvas


def deletion_test(model, images, seed=0):
    """Faithfulness of Grad-CAM: blur the attended region vs an equal-area random
    region and compare the fall in P(cancer)."""
    rng = np.random.default_rng(seed)
    base, attended, random_ = [], [], []
    for im in images:
        cam = grad_cam(*model, im)
        w, h = im.size
        cam_up = np.asarray(Image.fromarray(np.uint8(255 * cam)).resize((w, h), Image.BILINEAR)) / 255.0
        mask = cam_up >= CAM_THRESHOLD
        blurred = im.filter(ImageFilter.GaussianBlur(radius=max(w, h) / 25))
        rand = np.zeros_like(mask)
        flat = rng.permutation(mask.size)[: int(mask.sum())]
        rand.flat[flat] = True  # same number of pixels, scattered
        # Scattered pixels are easy to ignore, so also use a random box of the same area.
        side = int(np.sqrt(max(mask.sum(), 1)))
        x0, y0 = rng.integers(0, max(w - side, 1)), rng.integers(0, max(h - side, 1))
        box = np.zeros_like(mask)
        box[y0 : y0 + side, x0 : x0 + side] = True
        arr, blur_arr = np.asarray(im), np.asarray(blurred)
        att_img = Image.fromarray(np.where(mask[..., None], blur_arr, arr))
        box_img = Image.fromarray(np.where(box[..., None], blur_arr, arr))
        p = st.run(*model, [im, att_img, box_img])[0]
        base.append(p[0])
        attended.append(p[1])
        random_.append(p[2])
    base, attended, random_ = map(np.array, (base, attended, random_))
    return {
        "photos": len(images),
        "mean_p_cancer_original": float(base.mean()),
        "mean_drop_blurring_gradcam_region": float((base - attended).mean()),
        "mean_drop_blurring_random_region_same_area": float((base - random_).mean()),
        "share_where_gradcam_region_matters_more": float(((base - attended) > (base - random_)).mean()),
    }


def cmd_eval(final: bool) -> None:
    g = st.load_model(GLOBAL_CKPT)
    loc = st.load_model(LOCAL_CKPT)
    out = {"config": {"cam_threshold": CAM_THRESHOLD, "margin": MARGIN, "min_side": MIN_SIDE}}

    _, val_im, val_y = labelled(DATA / "case_split_fixed" / "val")
    _, test_im, test_y = labelled(DATA / "kaggle_split_fixed" / "test")
    vg, vl = scores(g, loc, val_im)
    tg, tl = scores(g, loc, test_im)

    # Stage 4: fusion weight chosen on validation (AUC), then fixed.
    grid = np.round(np.linspace(0, 1, 11), 2)
    w = float(max(grid, key=lambda a: roc_auc_score(val_y, a * vg + (1 - a) * vl)))
    out["fusion_weight_global"] = w
    vf, tf_ = w * vg + (1 - w) * vl, w * tg + (1 - w) * tl

    def block(y, pg, pl, pf):
        return {
            name: {"auc": float(roc_auc_score(y, p)), **threshold_metrics(p, y)}
            for name, p in (("global_only", pg), ("local_only", pl), ("hybrid", pf))
        }

    out["validation"] = block(val_y, vg, vl, vf)
    out["development_test"] = block(test_y, tg, tl, tf_)
    out["development_test_auc_gain_hybrid_minus_global"] = auc_ci_diff(test_y, tf_, tg)

    # Stage 5: conformal thresholds on validation for both scores, same alpha/beta.
    for name, v, t in (("global_only", vg, tg), ("hybrid", vf, tf_)):
        lo, hi = lam_lo_crc(v[val_y], 0.05), lam_hi_for(v[~val_y], 0.10)
        out.setdefault("triage_development_test", {})[name] = {"lo": lo, "hi": hi, **triage(t, test_y, lo, hi)}

    # Robustness: test cancers made small in the frame.
    zc = [zoomed_out(im) for im, y in zip(test_im, test_y, strict=True) if y]
    zg, zl = scores(g, loc, zc)
    out["zoomed_out_test_cancers_caught"] = {
        "global_only": f"{int((zg >= 0.5).sum())}/{len(zc)}",
        "hybrid": f"{int(((w * zg + (1 - w) * zl) >= 0.5).sum())}/{len(zc)}",
    }

    # Clinic held-out (all dysplasia, no cancer): false cancer calls.
    hold = [
        st.open_rgb(DATA / "case_split" / "holdout" / r["filename"])
        for r in csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv", encoding="utf-8"))
    ]
    hg, hl = scores(g, loc, hold)
    out["clinic_heldout_called_cancer"] = {
        "global_only": f"{int((hg >= 0.5).sum())}/{len(hold)}",
        "hybrid": f"{int(((w * hg + (1 - w) * hl) >= 0.5).sum())}/{len(hold)}",
    }

    # Explainability: is Grad-CAM faithful? (test cancers)
    out["gradcam_deletion_test_cancers"] = deletion_test(g, [im for im, y in zip(test_im, test_y, strict=True) if y])

    if final:
        _, f_im, f_y = labelled(DATA / "fresh_test")
        fg, fl = scores(g, loc, f_im)
        ff = w * fg + (1 - w) * fl
        out["untouched_test_second_use"] = block(f_y, fg, fl, ff)
        for name, v, t in (("global_only", vg, fg), ("hybrid", vf, ff)):
            lo, hi = lam_lo_crc(v[val_y], 0.05), lam_hi_for(v[~val_y], 0.10)
            out["untouched_test_second_use"][name]["triage"] = triage(t, f_y, lo, hi)

    print(json.dumps(out, indent=2))
    (ART / "xai_hybrid.json").write_text(json.dumps(out, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["crops", "eval"])
    ap.add_argument("--final", action="store_true", help="also report the untouched set (its second use)")
    args = ap.parse_args()
    if args.command == "crops":
        cmd_crops()
    else:
        cmd_eval(args.final)


if __name__ == "__main__":
    main()
