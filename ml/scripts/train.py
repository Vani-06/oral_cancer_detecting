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
import time
from pathlib import Path

import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import ResNet50_Weights, resnet50

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kaggle_split"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
IMG_SIZE = 224

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_model() -> nn.Module:
    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)

    for param in model.parameters():
        param.requires_grad = False
    for param in model.layer4.parameters():
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
    args = parser.parse_args()

    device = torch.device("cpu")
    train_tf, eval_tf = build_transforms()

    train_ds = datasets.ImageFolder(DATA_DIR / "train", transform=train_tf)
    val_ds = datasets.ImageFolder(DATA_DIR / "val", transform=eval_tf)

    # ImageFolder assigns class indices alphabetically -- confirm it matches
    # what evaluate.py / the backend inference service will assume.
    print("Class-to-index mapping:", train_ds.class_to_idx)
    assert train_ds.class_to_idx == {"Cancer": 0, "Non-Cancer": 1}, (
        "Class index mapping changed -- update evaluate.py and the inference "
        "service's label lookup to match, or this run's checkpoint will be "
        "silently mislabeled."
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    model = build_model().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    log_rows = []
    best_val_acc = 0.0
    best_path = ARTIFACTS_DIR / "resnet50_oral_cancer.pt"

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

    with (ARTIFACTS_DIR / "training_log.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        writer.writeheader()
        writer.writerows(log_rows)

    print(f"\nBest validation accuracy: {best_val_acc:.3f}")
    print(f"Checkpoint: {best_path}")


if __name__ == "__main__":
    main()
