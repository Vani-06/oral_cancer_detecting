"""
Look for shortcuts behind false Cancer calls: things that are not pathology
(textbook arrows and captions, borders, blur, colour cast, glare, a glove in
frame, zoom) but that the model may have learned to associate with cancer
because of how the training photos were taken.

Each probe is applied to photos with no cancer (Kaggle test Non-Cancer and
the client's held-out dysplasia patients) and to cancer photos (Kaggle test
Cancer), none used in training. A probe that raises the false Cancer rate,
or lowers the share of cancers caught, is a shortcut; ZoomHealthy / ShortcutAugment in train.py then remove the
cue by applying it to training photos of both classes.

Usage:
    .venv/Scripts/python.exe scripts/probe_shortcuts.py artifacts/resnet50_oral_cancer_v4.pt [more checkpoints]
"""

import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent


def arrow(im):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    x0, y0, x1, y1 = int(w * 0.25), int(h * 0.25), int(w * 0.42), int(h * 0.45)
    lw = max(3, w // 120)
    d.line((x0, y0, x1, y1), fill="black", width=lw)
    d.polygon([(x1, y1), (x1 - w * 0.05, y1 - h * 0.01), (x1 - w * 0.01, y1 - h * 0.06)], fill="black")
    return im


def caption(im):
    w, h = im.size
    out = Image.new("RGB", (w, int(h * 1.08)), "white")
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((w * 0.1, h * 1.02), "From: Oral pathology, ed 6, 2014", fill="black")
    return out


def border(im, colour, frac=0.12):
    return ImageOps.expand(im, border=int(min(im.size) * frac), fill=colour)


def glare(im):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    for cx, cy in [(0.6, 0.3), (0.7, 0.5), (0.35, 0.65)]:
        r = min(w, h) * 0.03
        d.ellipse((w * cx - r, h * cy - r, w * cx + r, h * cy + r), fill="white")
    return im


def glove(im):
    im = im.copy()
    w, h = im.size
    ImageDraw.Draw(im).rounded_rectangle((w * 0.72, h * 0.05, w * 1.1, h * 0.45), radius=int(w * 0.08),
                                         fill=(235, 238, 242))
    return im


def warm(im):
    r, g, b = im.split()
    return Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.12))), g, b.point(lambda v: int(v * 0.88))))


PROBES = {
    "arrow drawn on photo": arrow,
    "textbook caption strip": caption,
    "black border": lambda im: border(im, "black"),
    "white border": lambda im: border(im, "white"),
    "blurred": lambda im: im.filter(ImageFilter.GaussianBlur(radius=max(1, im.width // 150))),
    "low resolution": lambda im: im.resize((max(1, im.width // 5), max(1, im.height // 5))).resize(im.size),
    "heavy JPEG": lambda im: st.jpeg(im, 15),
    "warmer / redder": warm,
    "more saturated": lambda im: ImageEnhance.Color(im).enhance(1.5),
    "flash glare spots": glare,
    "white glove in frame": glove,
    "rotated 90": lambda im: im.rotate(90, expand=True),
    "zoom to centre 40%": lambda im: st.center_crop(im, 0.4),
    "zoomed out (small in frame)": lambda im: border(im, (205, 160, 140), frac=0.45),
    "darker (dim light)": lambda im: ImageEnhance.Brightness(im).enhance(0.6),
}


def main():
    data = ML_DIR / "data"
    sets = {
        "Kaggle healthy": [st.open_rgb(p) for p in sorted((data / "kaggle_split_fixed/test/Non-Cancer").glob("*"))],
        "client dysplasia": [st.open_rgb(data / "case_split/holdout" / r["filename"])
                             for r in csv.DictReader(open(data / "case_split/holdout/manifest.csv"))],
        "CANCER caught": [st.open_rgb(p) for p in sorted((data / "kaggle_split_fixed/test/Cancer").glob("*"))],
    }
    for ckpt in sys.argv[1:]:
        model = st.load_model(Path(ckpt))
        print(f"\n== {Path(ckpt).name}: Cancer-call rate, change vs unedited (CANCER caught: higher is better)")
        base = {k: st.run(*model, ims)[0] >= 0.5 for k, ims in sets.items()}
        print(f"   {'unedited':24s} " + "   ".join(f"{k} {v.mean():5.1%}" for k, v in base.items()), flush=True)
        for name, fn in PROBES.items():
            cells = []
            for k, ims in sets.items():
                rate = (st.run(*model, [fn(im) for im in ims])[0] >= 0.5).mean()
                cells.append(f"{k} {rate:5.1%} ({rate - base[k].mean():+5.1%})")
            print(f"   {name:24s} " + "   ".join(cells), flush=True)


if __name__ == "__main__":
    main()
