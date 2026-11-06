"""
Review item 23: how the photo check (PhotoGate) treats images that are not
usable oral photos.

Groups:
  * non-oral: histopathology slide photos (a folder given on the command line),
    plus synthetic images (blank, noise, a text page, gradients, checkerboard);
  * poor oral photos: development-test oral photos degraded heavily (strong
    blur, very dark, over-exposed, tiny upscaled, mostly cropped away);
  * real clinical oral photos (a folder given on the command line) -- these
    should be accepted.

Only aggregate counts are written (artifacts/gate_ood_test.json); no image or
file name leaves the machine.

Run with the backend environment (it imports the app's PhotoGate):
    backend/.venv/Scripts/python.exe ml/scripts/gate_ood_test.py \
        --non-oral "<histopathology folder>" --clinical "<clinical photos folder>"
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.inference_service import PhotoGate, _open_photo  # noqa: E402
from app.services.photo_quality import quality_problem  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def folder(path):
    return [_open_photo(p) for p in sorted(Path(path).rglob("*")) if p.suffix.lower() in EXTS]


def synthetic(n_each=5, seed=0):
    rng = np.random.default_rng(seed)
    out = {"blank colour": [], "random noise": [], "text page": [], "gradient": [], "checkerboard": []}
    for i in range(n_each):
        out["blank colour"].append(Image.new("RGB", (480, 360), tuple(int(v) for v in rng.integers(0, 256, 3))))
        out["random noise"].append(Image.fromarray(rng.integers(0, 256, (360, 480, 3), dtype=np.uint8)))
        page = Image.new("RGB", (480, 640), "white")
        draw = ImageDraw.Draw(page)
        for line in range(30):
            draw.text((20, 15 + line * 20), "Patient report line %d lorem ipsum dolor sit amet" % (line + i), fill="black")
        out["text page"].append(page)
        a = np.linspace(0, 255, 480)[None, :, None] * np.ones((360, 1, 3))
        a[..., i % 3] = 255 - a[..., i % 3]
        out["gradient"].append(Image.fromarray(a.astype(np.uint8)))
        size = 20 + 10 * i
        board = ((np.indices((360, 480)) // size).sum(0) % 2 * 255).astype(np.uint8)
        out["checkerboard"].append(Image.fromarray(board).convert("RGB"))
    return out


DEGRADE = {
    "strong blur": lambda im: im.filter(ImageFilter.GaussianBlur(radius=max(im.size) / 40)),
    "very dark": lambda im: ImageEnhance.Brightness(im).enhance(0.15),
    "over-exposed": lambda im: ImageEnhance.Brightness(im).enhance(3.0),
    "tiny (32 px) upscaled": lambda im: im.resize((32, 32)).resize(im.size),
    "mostly cropped away (corner 15%)": lambda im: im.crop((0, 0, int(im.width * 0.15), int(im.height * 0.15))),
}


def rate(gate, images):
    """Accepted by the photo check alone, and by the photo check plus the
    quality check (what the app does)."""
    gate_ok = [gate.accepts(im) for im in images]
    both = [ok and quality_problem(im) is None for ok, im in zip(gate_ok, images)]
    n = max(len(images), 1)
    return {"n": len(images), "accepted_by_photo_check": int(sum(gate_ok)),
            "accepted_by_app": int(sum(both)), "accepted_share_app": round(sum(both) / n, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=str(ROOT / "ml" / "artifacts" / "oral_photo_gate_v1.pt"))
    ap.add_argument("--non-oral", help="folder of non-oral images (e.g. histopathology slides)")
    ap.add_argument("--clinical", help="folder of real clinical oral photos")
    args = ap.parse_args()
    gate = PhotoGate(Path(args.gate))
    out = {"threshold": gate.threshold, "groups": {}}

    if args.non_oral:
        out["groups"]["non-oral: histopathology slides"] = rate(gate, folder(args.non_oral))
    for name, ims in synthetic().items():
        out["groups"][f"non-oral: synthetic {name}"] = rate(gate, ims)

    test = folder(ROOT / "ml" / "data" / "kaggle_split_fixed" / "test")
    out["groups"]["oral, unedited (development test)"] = rate(gate, test)
    for name, fn in DEGRADE.items():
        out["groups"][f"poor oral: {name}"] = rate(gate, [fn(im) for im in test])

    if args.clinical:
        out["groups"]["real clinical oral photos"] = rate(gate, folder(args.clinical))

    print(json.dumps(out, indent=2))
    (ROOT / "ml" / "artifacts" / "gate_ood_test.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
