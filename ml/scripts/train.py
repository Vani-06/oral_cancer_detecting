"""
Fine-tune ResNet-50 (ImageNet-pretrained) for binary oral lesion classification.

Only layer4 and the final fc are unfrozen -- everything earlier stays at its
ImageNet weights. This is the standard, conservative choice for a dataset this
small (~630 training images after dedup): fine-tuning the whole network risks
overfitting fast, while training only the fc head on frozen features usually
underfits for a domain this different from ImageNet's natural-image distribution.
Augmentation is deliberately mild (flip, small rotation, small color jitter) --
lesion color and texture are the diagnostic signal, so anything more aggressive
would corrupt exactly what the model needs to learn.

Usage:
    .venv/Scripts/python.exe scripts/train.py [--epochs 15] [--lr 1e-4]

Reads:
    ml/data/kaggle_split/{train,val}/{Cancer,Non-Cancer}/*.jpeg
Writes:
    ml/artifacts/resnet50_oral_cancer.pt
    ml/artifacts/training_log.csv
"""

import argparse
import csv
import io
import random
import time
from pathlib import Path

import torch
from torch import nn, optim
from torch.utils.data import DataLoader, WeightedRandomSampler
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from torchvision import datasets, transforms
from torchvision.models import ResNet50_Weights, resnet50

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kaggle_split"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
IMG_SIZE = 224

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_model(unfreeze_layer3: bool = False) -> nn.Module:
    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)

    for param in model.parameters():
        param.requires_grad = False
    for param in model.layer4.parameters():
        param.requires_grad = True
    if unfreeze_layer3:
        # Deeper fine-tune: layer3 holds mid-level texture/color features.
        # If the client's real photos differ from Kaggle's in exactly those
        # terms (lighting, camera, compression), layer4-only fine-tuning may
        # not be able to adapt far enough -- worth testing directly rather
        # than assuming more data is the only lever left.
        for param in model.layer3.parameters():
            param.requires_grad = True

    model.fc = nn.Linear(model.fc.in_features, 2)  # Cancer / Non-Cancer
    return model


def build_transforms():
    train_tf = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )
    eval_tf = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )
    return train_tf, eval_tf


def _shortcut_edits(image):
    """Randomised edits that never change the diagnosis but that the round-4
    model reacted to (scripts/probe_shortcuts.py): zoomed out, borders,
    textbook arrows, flash glare, a glove in frame, blur, low resolution,
    JPEG, dim or bright light, colour cast, 90-degree rotations. Applied to
    both classes, so none of them can stand in for the label."""
    w, h = image.size
    if random.random() < 0.25:  # zoomed out: lesion small in a skin-toned or plain surround
        pad = int(min(w, h) * random.uniform(0.1, 0.5))
        fill = random.choice([(0, 0, 0), (255, 255, 255), tuple(random.randint(120, 230) for _ in range(3))])
        image = ImageOps.expand(image, border=pad, fill=fill)
        w, h = image.size
    draw = ImageDraw.Draw(image)
    if random.random() < 0.15:  # textbook arrow
        x0, y0 = random.uniform(0.1, 0.7) * w, random.uniform(0.1, 0.7) * h
        x1, y1 = x0 + random.uniform(-0.2, 0.2) * w, y0 + random.uniform(0.05, 0.2) * h
        draw.line((x0, y0, x1, y1), fill=random.choice(["black", "white", "yellow"]), width=max(2, w // 120))
    if random.random() < 0.2:  # flash glare
        for _ in range(random.randint(1, 4)):
            r = min(w, h) * random.uniform(0.01, 0.04)
            cx, cy = random.uniform(0, w), random.uniform(0, h)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(250, 250, 250))
    if random.random() < 0.15:  # glove / instrument at an edge
        x0, y0 = random.uniform(0.6, 0.85) * w, random.uniform(-0.1, 0.5) * h
        shade = random.randint(200, 245)
        draw.rounded_rectangle((x0, y0, w * 1.1, y0 + h * random.uniform(0.2, 0.5)), radius=int(w * 0.05),
                               fill=(shade, shade, min(255, shade + 8)))
    if random.random() < 0.2:
        image = image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 3) * max(1, w / 400)))
    if random.random() < 0.2:
        f = random.uniform(0.15, 0.5)
        image = image.resize((max(8, int(w * f)), max(8, int(h * f)))).resize((w, h))
    if random.random() < 0.2:
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=random.randint(10, 40))
        image = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if random.random() < 0.3:
        image = ImageEnhance.Brightness(image).enhance(random.uniform(0.6, 1.3))
    if random.random() < 0.3:
        image = ImageEnhance.Color(image).enhance(random.uniform(0.7, 1.5))
    if random.random() < 0.2:
        r, g, b = image.split()
        k = random.uniform(0.88, 1.12)
        image = Image.merge("RGB", (r.point(lambda v: min(255, int(v * k))), g, b.point(lambda v: min(255, int(v / k)))))
    if random.random() < 0.3:
        image = image.rotate(random.choice([90, 180, 270]), expand=True)
    return image


class ZoomHealthy(datasets.ImageFolder):
    """Close-up crops of healthy photos, labelled healthy.

    The Kaggle healthy photos are mostly whole-mouth phone pictures while its
    cancer photos are mostly clinical close-ups, so a model can learn "close-up
    means cancer": zooming into healthy test photos took false Cancer calls
    from 1.5% to ~20% (October 2026 stress test). Any crop of a healthy mouth
    is still healthy, so with probability `p` a healthy image becomes a
    random 15-60% crop. Cancer images are never zoomed hard -- a crop could
    cut the lesion out -- but every image gets a mild 70-100% crop so that
    "looks zoomed" does not itself become a healthy cue.
    """

    def __init__(self, root, p: float, shortcut_edits: bool = False, zoom_cancer: bool = False):
        super().__init__(root)
        self.p = p
        self.zoom_cancer = zoom_cancer
        self.shortcut_edits = shortcut_edits
        self.healthy_idx = self.class_to_idx["Non-Cancer"]
        tail = [
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
        self.mild = transforms.Compose([transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)), *tail])
        self.zoom = transforms.Compose([transforms.RandomResizedCrop(IMG_SIZE, scale=(0.15, 0.6)), *tail])
        self.zoom_lesion = transforms.Compose([transforms.RandomResizedCrop(IMG_SIZE, scale=(0.35, 0.8)), *tail])

    def __getitem__(self, index):
        path, target = self.samples[index]
        image = self.loader(path)
        if self.shortcut_edits:
            image = _shortcut_edits(image)
        if target == self.healthy_idx:
            zoom, tf = random.random() < self.p, self.zoom
        else:
            # --zoom-all (review item 21): close-ups of cancers too, so that
            # "zoomed in" stops predicting "healthy". Milder crops keep the
            # lesion in frame most of the time.
            zoom, tf = self.zoom_cancer and random.random() < self.p, self.zoom_lesion
        return (tf if zoom else self.mild)(image), target


def run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0

    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)

            if train:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if train:
                loss.backward()
                optimizer.step()

            total_loss += loss.item() * images.size(0)
            correct += (outputs.argmax(1) == labels).sum().item()
            total += images.size(0)

    return total_loss / total, correct / total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--train-dir", type=Path, default=DATA_DIR / "train",
        help="ImageFolder-style directory to train on (default: Kaggle-only split)",
    )
    parser.add_argument(
        "--val-dir", type=Path, default=DATA_DIR / "val",
        help="ImageFolder-style directory to validate on (default: Kaggle-only split)",
    )
    parser.add_argument(
        "--checkpoint-name", default="resnet50_oral_cancer.pt",
        help="Output filename under ml/artifacts/ (default overwrites the base checkpoint)",
    )
    parser.add_argument(
        "--client-oversample-factor", type=float, default=1.0,
        help=(
            "Sampling weight multiplier for training images whose filename "
            "starts with 'client_' (see prepare_combined_training.py). At "
            "1.0 (default), every image is drawn with equal probability, so "
            "client images -- ~11%% of the combined training set -- are "
            "proportionally rare in every epoch's gradient signal. A factor "
            "above 1.0 uses WeightedRandomSampler to draw them more often, "
            "without duplicating any file on disk."
        ),
    )
    parser.add_argument(
        "--zoom-all", action="store_true",
        help="Also apply close-up crops (35-80%% of the image) to cancer photos.",
    )
    parser.add_argument(
        "--zoom-healthy", type=float, default=0.0,
        help="Probability of replacing a healthy training image with a close-up crop (see ZoomHealthy).",
    )
    parser.add_argument(
        "--shortcut-edits", action="store_true",
        help="Also apply diagnosis-preserving edits to both classes (see _shortcut_edits).",
    )
    parser.add_argument(
        "--unfreeze-layer3", action="store_true",
        help="Also fine-tune layer3, not just layer4+fc -- see build_model().",
    )
    args = parser.parse_args()

    device = torch.device("cpu")
    train_tf, eval_tf = build_transforms()

    if args.zoom_healthy > 0:
        train_ds = ZoomHealthy(args.train_dir, p=args.zoom_healthy, shortcut_edits=args.shortcut_edits,
                               zoom_cancer=args.zoom_all)
    else:
        train_ds = datasets.ImageFolder(args.train_dir, transform=train_tf)
    val_ds = datasets.ImageFolder(args.val_dir, transform=eval_tf)

    # ImageFolder assigns class indices alphabetically -- confirm it matches
    # what evaluate.py / the backend inference service will assume.
    print("Class-to-index mapping:", train_ds.class_to_idx)
    assert train_ds.class_to_idx == {"Cancer": 0, "Non-Cancer": 1}, (
        "Class index mapping changed -- update evaluate.py and the inference "
        "service's label lookup to match, or this run's checkpoint will be "
        "silently mislabeled."
    )

    if args.client_oversample_factor != 1.0:
        sample_paths = [s[0] for s in train_ds.samples]
        weights = [
            args.client_oversample_factor if Path(p).name.startswith("client_") else 1.0
            for p in sample_paths
        ]
        n_client = sum(1 for p in sample_paths if Path(p).name.startswith("client_"))
        print(
            f"Client oversampling active: factor={args.client_oversample_factor}, "
            f"{n_client}/{len(sample_paths)} training images are client-domain "
            f"(effective share per epoch: "
            f"{100 * n_client * args.client_oversample_factor / sum(weights):.1f}%)"
        )
        sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler)
    else:
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    model = build_model(unfreeze_layer3=args.unfreeze_layer3).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    log_rows = []
    best_val_acc = 0.0
    best_path = ARTIFACTS_DIR / args.checkpoint_name

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        elapsed = time.time() - t0

        print(
            f"epoch {epoch:2d}/{args.epochs} | "
            f"train loss {train_loss:.4f} acc {train_acc:.3f} | "
            f"val loss {val_loss:.4f} acc {val_acc:.3f} | {elapsed:.1f}s"
        )
        log_rows.append(
            {"epoch": epoch, "train_loss": train_loss, "train_acc": train_acc,
             "val_loss": val_loss, "val_acc": val_acc, "seconds": round(elapsed, 1)}
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "class_to_idx": train_ds.class_to_idx,
                    "img_size": IMG_SIZE,
                    "mean": IMAGENET_MEAN,
                    "std": IMAGENET_STD,
                    "epoch": epoch,
                    "val_acc": val_acc,
                },
                best_path,
            )
            print(f"  -> new best (val_acc={val_acc:.3f}), saved to {best_path}")

    log_name = f"training_log_{args.checkpoint_name.replace('.pt', '')}.csv"
    with (ARTIFACTS_DIR / log_name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        writer.writeheader()
        writer.writerows(log_rows)

    print(f"\nBest validation accuracy: {best_val_acc:.3f}")
    print(f"Checkpoint: {best_path}")


if __name__ == "__main__":
    main()
