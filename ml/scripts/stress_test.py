"""
Stress-test the cancer checkpoint the way real users will hit it:

1. In-distribution photos (client holdout patients + Kaggle test split) --
   baseline accuracy, then the same photos after harmless changes a phone or
   upload might make (flip, rotation, lower resolution, JPEG compression,
   lighting, tighter crop). A trustworthy model should not change its answer.
2. Images that are not oral photos at all (histopathology slides, desktop
   wallpapers, synthetic noise / flat colours / patterns). The model has no
   "none of the above" output, so every one of these gets Cancer or
   Non-Cancer -- this measures how often, and whether its internal features
   can tell them apart from real oral photos.

Caches each image's P(Cancer) and 2048-d penultimate features to
artifacts/stress_test_cache.npz so analyses can be rerun without inference.

Usage:
    .venv/Scripts/python.exe scripts/stress_test.py [--checkpoint artifacts/resnet50_oral_cancer_v4.pt]
"""

import argparse
import csv
import io
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageEnhance, ImageOps
from torchvision import transforms
from torchvision.models import resnet50

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
HISTOPATH_DIR = Path.home() / "Downloads" / "histopath thesis images-20260324T090403Z-1-001"
WALLPAPER_DIR = Path("C:/Windows/Web")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_model(path: Path):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    tf = transforms.Compose([
        transforms.Resize((ckpt["img_size"], ckpt["img_size"])),
        transforms.ToTensor(),
        transforms.Normalize(ckpt["mean"], ckpt["std"]),
    ])
    return model, tf, ckpt["class_to_idx"]["Cancer"]


@torch.no_grad()
def run(model, tf, cancer_idx, images: list[Image.Image]):
    """Returns (P(Cancer), penultimate features) for each image."""
    feats = []
    hook = model.avgpool.register_forward_hook(lambda m, i, o: feats.append(o.flatten(1)))
    probs = []
    try:
        for start in range(0, len(images), 16):
            batch = torch.stack([tf(im) for im in images[start:start + 16]])
            probs.append(torch.softmax(model(batch), 1)[:, cancer_idx])
    finally:
        hook.remove()
    return torch.cat(probs).numpy(), torch.cat(feats).numpy()


def open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def jpeg(im: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def center_crop(im: Image.Image, frac: float) -> Image.Image:
    w, h = im.size
    dw, dh = int(w * (1 - frac) / 2), int(h * (1 - frac) / 2)
    return im.crop((dw, dh, w - dw, h - dh))


VARIANTS = {
    "mirror": lambda im: ImageOps.mirror(im),
    "rotate_90": lambda im: im.rotate(90, expand=True),
    "rotate_180": lambda im: im.rotate(180),
    "tilt_10deg": lambda im: im.rotate(10, resample=Image.BILINEAR),
    "low_res_25pct": lambda im: im.resize((max(1, im.width // 4), max(1, im.height // 4))).resize(im.size),
    "jpeg_q25": lambda im: jpeg(im, 25),
    "darker_20pct": lambda im: ImageEnhance.Brightness(im).enhance(0.8),
    "brighter_20pct": lambda im: ImageEnhance.Brightness(im).enhance(1.2),
    "crop_80pct": lambda im: center_crop(im, 0.8),
}


def synthetic_images(rng: np.random.Generator) -> dict[str, Image.Image]:
    out = {}
    for name, rgb in {"white": (255, 255, 255), "black": (0, 0, 0), "red": (200, 30, 30),
                      "pink": (230, 150, 150), "grey": (128, 128, 128)}.items():
        out[f"flat_{name}"] = Image.new("RGB", (640, 480), rgb)
    for i in range(5):
        out[f"noise_{i}"] = Image.fromarray(rng.integers(0, 256, (480, 640, 3), dtype=np.uint8))
    for i in range(3):
        # Pinkish noise: closer to mucosa colours than uniform noise.
        base = np.array([200, 110, 110]) + rng.normal(0, 35, (480, 640, 3))
        out[f"pink_noise_{i}"] = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    grad = np.linspace(0, 255, 640, dtype=np.uint8)
    out["gradient"] = Image.fromarray(np.stack([np.tile(grad, (480, 1))] * 3, -1))
    check = (np.indices((480, 640)) // 40).sum(0) % 2 * 255
    out["checkerboard"] = Image.fromarray(np.stack([check.astype(np.uint8)] * 3, -1))
    doc = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(doc)
    for y in range(20, 460, 24):
        draw.text((20, y), "Patient report -- lorem ipsum dolor sit amet 0123456789", fill="black")
    out["text_document"] = doc
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ML_DIR / "artifacts" / "resnet50_oral_cancer_v4.pt"))
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    model, tf, cancer_idx = load_model(Path(args.checkpoint))
    rng = np.random.default_rng(0)
    cache: dict[str, np.ndarray] = {}

    def record(key: str, images: list[Image.Image], labels: list[int] | None, names: list[str]):
        probs, feats = run(model, tf, cancer_idx, images)
        cache[f"{key}/p"], cache[f"{key}/f"], cache[f"{key}/names"] = probs, feats, np.array(names)
        if labels is not None:
            cache[f"{key}/y"] = np.array(labels)
        print(f"{key}: {len(images)} images", flush=True)
        return probs

    # Reference set for "what an oral photo looks like": the training split.
    for split in ["train", "val"]:
        paths = sorted(p for p in (DATA / "case_split" / split).rglob("*") if p.suffix.lower() in IMAGE_EXTS)
        record(f"ref_{split}", [open_rgb(p) for p in paths], [int(p.parent.name == "Cancer") for p in paths],
               [p.name for p in paths])

    # In-distribution test sets, never trained on.
    holdout = list(csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv")))
    kaggle = sorted(p for p in (DATA / "kaggle_split" / "test").rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    sets = {
        "client_holdout": ([open_rgb(DATA / "case_split" / "holdout" / r["filename"]) for r in holdout],
                           [int(r["label"] == "Cancer") for r in holdout], [r["filename"] for r in holdout]),
        "kaggle_test": ([open_rgb(p) for p in kaggle], [int(p.parent.name == "Cancer") for p in kaggle],
                        [f"{p.parent.name}/{p.name}" for p in kaggle]),
    }
    for name, (images, labels, names) in sets.items():
        record(f"{name}/original", images, labels, names)
        for vname, fn in VARIANTS.items():
            record(f"{name}/{vname}", [fn(im) for im in images], labels, names)

    # Not oral photos.
    histo = sorted(p for p in HISTOPATH_DIR.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    record("ood/histopathology", [open_rgb(p) for p in histo], None, [p.name for p in histo])
    walls = sorted(p for p in WALLPAPER_DIR.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    record("ood/wallpaper", [open_rgb(p) for p in walls], None, [p.name for p in walls])
    synth = synthetic_images(rng)
    record("ood/synthetic", list(synth.values()), None, list(synth.keys()))

    out = ML_DIR / "artifacts" / "stress_test_cache.npz"
    np.savez_compressed(out, **cache)
    print("wrote", out)


if __name__ == "__main__":
    main()
