"""
Build the "is this a clinical photo of the mouth?" check that runs before
cancer detection.

The cancer model has no "none of the above" output: a histopathology slide,
a wallpaper or a blank image still comes back Cancer or Non-Cancer (the
stress test, scripts/stress_test.py, measured 90-100% of such images being
called Non-Cancer -- false reassurance). This gate refuses them instead.

Method: ImageNet ResNet-50 features (general-purpose, unlike the cancer
model's own features, which separated these images poorly) and the mean
cosine distance to the 5 nearest training photos. It is fitted on oral
photos only; the cut-off is a percentile of distances on the validation
split, so no non-oral image is used to build it -- those are evaluation only.

Measured at the 99.5th percentile (the default), on images never used here:
  accepted: client holdout 100%, Kaggle test 100%
  rejected: histopathology slides 95%, wallpapers 100%, blank/noise/document 100%

Writes artifacts/oral_photo_gate_v1.pt, loaded by the backend via
GATE_MODEL_PATH (backend/app/services/inference_service.py).

Usage:
    .venv/Scripts/python.exe scripts/build_photo_gate.py [--percentile 99.5]
"""

import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

ML_DIR = Path(__file__).resolve().parent.parent
SPLIT_DIR = ML_DIR / "data" / "case_split"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MEAN, STD, SIZE, K = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225], 224, 5


@torch.no_grad()
def features(model, paths):
    tf = transforms.Compose([transforms.Resize((SIZE, SIZE)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    out = []
    for i in range(0, len(paths), 16):
        batch = []
        for p in paths[i:i + 16]:
            with Image.open(p) as im:
                batch.append(tf(ImageOps.exif_transpose(im).convert("RGB")))
        out.append(model(torch.stack(batch)))
    f = torch.cat(out)
    return f / f.norm(dim=1, keepdim=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--percentile", type=float, default=99.5)
    args = ap.parse_args()

    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2).eval()
    model.fc = torch.nn.Identity()
    paths = {s: sorted(p for p in (SPLIT_DIR / s).rglob("*") if p.suffix.lower() in IMAGE_EXTS) for s in ("train", "val")}
    bank = features(model, paths["train"])
    val = features(model, paths["val"])
    val_dist = 1 - (val @ bank.T).topk(K, dim=1).values.mean(1)
    threshold = float(np.percentile(val_dist.numpy(), args.percentile))
    print(f"bank {len(bank)} photos, threshold {threshold:.4f} ({args.percentile}th pct of {len(val)} validation photos)")

    out = ML_DIR / "artifacts" / "oral_photo_gate_v1.pt"
    torch.save({
        "backbone_state_dict": model.state_dict(),
        "bank": bank.half(),
        "k": K,
        "threshold": threshold,
        "img_size": SIZE,
        "mean": MEAN,
        "std": STD,
        "percentile": args.percentile,
    }, out)
    print("wrote", out)


if __name__ == "__main__":
    main()
