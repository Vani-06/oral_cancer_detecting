"""
Train a ResNet-50 to grade oral epithelial dysplasia (mild / moderate / severe)
from clinical photos.

Only the client's own cases carry a dysplasia grade (Kaggle is binary), so
this trains on ml/data/client_cases: 196 photos from 99 patients (the single
carcinoma case is excluded -- cancer detection is the separate binary model).

With so few patients a single held-out split would be too noisy to trust, so
`cv` runs patient-grouped, grade-stratified k-fold cross-validation: both
photos of a patient always fall in the same fold, every patient is tested
exactly once, by a model that never saw them. The number of epochs is fixed
up front rather than picked per fold on the test fold, which would leak.

`final` then trains one model on all 99 patients with the same settings and
writes a checkpoint in the format backend/app/services/inference_service.py
loads.

Every client patient had dysplasia, so a three-grade model must pick a grade
even for a healthy mouth. `--with-normal` adds a fourth class, no dysplasia,
taught from the Kaggle Non-Cancer photos (mostly healthy mouths). `holdout`
then trains with the client's held-out patients (data/case_split/holdout)
and the Kaggle test split left out, and reports how both are graded.

Usage:
    .venv/Scripts/python.exe scripts/train_grading.py cv [--init v4|imagenet] [--folds 5]
    .venv/Scripts/python.exe scripts/train_grading.py final [--init v4|imagenet] [--with-normal]
    .venv/Scripts/python.exe scripts/train_grading.py holdout --with-normal [--init imagenet]
"""

import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from sklearn.metrics import cohen_kappa_score, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

ML_DIR = Path(__file__).resolve().parent.parent
CASES_DIR = ML_DIR / "data" / "client_cases"
ARTIFACTS_DIR = ML_DIR / "artifacts"
V4_CHECKPOINT = ARTIFACTS_DIR / "resnet50_oral_cancer_v4.pt"
KAGGLE_SPLIT_DIR = ML_DIR / "data" / "kaggle_split"
HOLDOUT_MANIFEST = ML_DIR / "data" / "case_split" / "holdout" / "manifest.csv"
NORMAL = "no_dysplasia"

GRADES = ["mild_dysplasia", "moderate_dysplasia", "severe_dysplasia"]
IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def load_cases():
    rows = [r for r in csv.DictReader(open(CASES_DIR / "manifest.csv")) if r["dx_group"] in GRADES]
    images = []
    for r in rows:
        with Image.open(CASES_DIR / r["filename"]) as im:
            # Cached once at the model's input size; augmentation runs on top.
            images.append(ImageOps.exif_transpose(im).convert("RGB").resize((IMG_SIZE, IMG_SIZE)))
    labels = np.array([GRADES.index(r["dx_group"]) for r in rows])
    groups = np.array([int(r["case_id"]) for r in rows])
    return rows, images, labels, groups


class CachedImages(Dataset):
    def __init__(self, images, labels, transform):
        self.images, self.labels, self.transform = images, labels, transform

    def __len__(self):
        return len(self.images)

    def __getitem__(self, i):
        return self.transform(self.images[i]), int(self.labels[i])


TRAIN_TF = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(10),
    transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])
EVAL_TF = transforms.Compose([transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB").resize((IMG_SIZE, IMG_SIZE))


def kaggle_images(splits, cls):
    paths = sorted(p for s in splits for p in (KAGGLE_SPLIT_DIR / s / cls).glob("*"))
    return [load_rgb(p) for p in paths]


def build_model(init: str, n_classes: int = len(GRADES)) -> nn.Module:
    if init == "v4":
        # Start from the cancer model: its backbone has already adapted to the
        # client's photo style (camera, lighting), which ImageNet has not.
        model = resnet50(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 2)
        model.load_state_dict(torch.load(V4_CHECKPOINT, map_location="cpu", weights_only=False)["state_dict"])
    else:
        model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
    for p in model.parameters():
        p.requires_grad = False
    for p in model.layer4.parameters():
        p.requires_grad = True
    model.fc = nn.Linear(model.fc.in_features, n_classes)
    return model


def train(model, images, labels, epochs, lr, seed):
    torch.manual_seed(seed)
    n_classes = model.fc.out_features
    counts = np.bincount(labels, minlength=n_classes)
    # Mild is the smallest grade; weight the loss so no class is ignored.
    weights = torch.tensor(len(labels) / (n_classes * np.maximum(counts, 1)), dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = optim.Adam([p for p in model.parameters() if p.requires_grad], lr=lr)
    loader = DataLoader(CachedImages(images, labels, TRAIN_TF), batch_size=16, shuffle=True,
                        generator=torch.Generator().manual_seed(seed))
    for epoch in range(1, epochs + 1):
        model.train()
        total, correct, loss_sum = 0, 0, 0.0
        for x, y in loader:
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            loss_sum += loss.item() * len(y)
            correct += (out.argmax(1) == y).sum().item()
            total += len(y)
        print(f"  epoch {epoch:2d}/{epochs} | train loss {loss_sum / total:.3f} acc {correct / total:.3f}", flush=True)
    return model


@torch.no_grad()
def predict_probs(model, images):
    model.eval()
    loader = DataLoader(CachedImages(images, np.zeros(len(images), dtype=int), EVAL_TF), batch_size=32)
    return torch.cat([torch.softmax(model(x), 1) for x, _ in loader]).numpy()


def report(labels, groups, probs, title):
    pred = probs.argmax(1)
    cm = confusion_matrix(labels, pred, labels=range(len(GRADES)))
    recall = cm.diagonal() / cm.sum(1)
    out = {
        "title": title,
        "photos": int(len(labels)),
        "accuracy": float((pred == labels).mean()),
        "balanced_accuracy": float(recall.mean()),
        "within_one_grade": float((np.abs(pred - labels) <= 1).mean()),
        "quadratic_kappa": float(cohen_kappa_score(labels, pred, weights="quadratic")),
        "recall": {g: float(r) for g, r in zip(GRADES, recall)},
        "confusion_rows_true_cols_pred": cm.tolist(),
        "majority_baseline_accuracy": float(np.bincount(labels).max() / len(labels)),
    }
    # Patient level: average the patient's photo probabilities.
    pat_true, pat_pred = [], []
    for g in np.unique(groups):
        m = groups == g
        pat_true.append(labels[m][0])
        pat_pred.append(probs[m].mean(0).argmax())
    pat_true, pat_pred = np.array(pat_true), np.array(pat_pred)
    out["patients"] = int(len(pat_true))
    out["patient_accuracy"] = float((pat_true == pat_pred).mean())
    out["patient_quadratic_kappa"] = float(cohen_kappa_score(pat_true, pat_pred, weights="quadratic"))
    print(json.dumps(out, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["cv", "final", "holdout"])
    ap.add_argument("--with-normal", action="store_true", help="add a no-dysplasia class from Kaggle Non-Cancer")
    ap.add_argument("--init", choices=["v4", "imagenet"], default="v4")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    rows, images, labels, groups = load_cases()
    print(f"{len(images)} photos, {len(set(groups))} patients, per grade {np.bincount(labels).tolist()}")

    classes = ([NORMAL] if args.with_normal else []) + GRADES
    if args.with_normal:
        labels = labels + 1  # grades shift up one; 0 is no dysplasia

    if args.mode == "holdout":
        assert args.with_normal, "holdout evaluates the four-class model"
        held = {int(r["case_id"]) for r in csv.DictReader(open(HOLDOUT_MANIFEST))}
        test_mask = np.isin(groups, list(held))
        normal = kaggle_images(["train", "val"], "Non-Cancer")
        tr_images = [im for im, t in zip(images, test_mask) if not t] + normal
        tr_labels = np.concatenate([labels[~test_mask], np.zeros(len(normal), dtype=int)])
        print(f"train: {(~test_mask).sum()} client photos + {len(normal)} healthy; test: {test_mask.sum()} client photos")
        model = train(build_model(args.init, len(classes)), tr_images, tr_labels, args.epochs, args.lr, args.seed)
        result = {}
        pred = predict_probs(model, [im for im, t in zip(images, test_mask) if t]).argmax(1)
        true = labels[test_mask]
        result["client_holdout"] = {
            "photos": int(len(true)),
            "grade_accuracy": float((pred == true).mean()),
            "called_no_dysplasia": float((pred == 0).mean()),
            "confusion_rows_true_cols_pred": confusion_matrix(true, pred, labels=range(len(classes))).tolist(),
        }
        for cls in ["Non-Cancer", "Cancer"]:
            pred = predict_probs(model, kaggle_images(["test"], cls)).argmax(1)
            result[f"kaggle_test_{cls}"] = {c: float((pred == i).mean()) for i, c in enumerate(classes)}
        print(json.dumps(result, indent=2))
        (ARTIFACTS_DIR / "grading_holdout_with_normal.json").write_text(json.dumps(result, indent=2))
    elif args.mode == "cv":
        # Folds take ~12 min each on CPU; save each one so an interrupted run
        # resumes instead of starting over.
        partial = ARTIFACTS_DIR / f"grading_cv_{args.init}_partial.npz"
        probs, done = np.zeros((len(labels), len(GRADES))), set()
        if partial.exists():
            saved = np.load(partial)
            probs, done = saved["probs"], set(saved["done"].tolist())
            print(f"resuming: folds {sorted(done)} already done")
        splitter = StratifiedGroupKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
        for k, (tr, te) in enumerate(splitter.split(images, labels, groups), 1):
            assert not set(groups[tr]) & set(groups[te]), "patient leaked across folds"
            if k in done:
                continue
            print(f"fold {k}: train {len(tr)} photos, test {len(te)} photos ({len(set(groups[te]))} patients)")
            model = train(build_model(args.init), [images[i] for i in tr], labels[tr], args.epochs, args.lr, args.seed + k)
            probs[te] = predict_probs(model, [images[i] for i in te])
            done.add(k)
            np.savez(partial, probs=probs, done=np.array(sorted(done)))
        result = report(labels, groups, probs, f"{args.folds}-fold patient-grouped CV, init={args.init}, epochs={args.epochs}")
        out = ARTIFACTS_DIR / f"grading_cv_{args.init}.json"
        out.write_text(json.dumps(result, indent=2))
        with open(ARTIFACTS_DIR / f"grading_cv_{args.init}_predictions.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["filename", "case_id", "true_grade", "pred_grade", *[f"p_{g}" for g in GRADES]])
            for r, y, p in zip(rows, labels, probs):
                w.writerow([r["filename"], r["case_id"], GRADES[y], GRADES[p.argmax()], *[f"{v:.4f}" for v in p]])
        partial.unlink()
        print("wrote", out)
    else:
        if args.with_normal:
            normal = kaggle_images(["train", "val"], "Non-Cancer")
            images, labels = images + normal, np.concatenate([labels, np.zeros(len(normal), dtype=int)])
        model = train(build_model(args.init, len(classes)), images, labels, args.epochs, args.lr, args.seed)
        ckpt = ARTIFACTS_DIR / f"resnet50_dysplasia_grade_{'v2' if args.with_normal else 'v1'}.pt"
        torch.save({
            "state_dict": model.state_dict(),
            "class_to_idx": {g: i for i, g in enumerate(classes)},
            "img_size": IMG_SIZE,
            "mean": IMAGENET_MEAN,
            "std": IMAGENET_STD,
            "init": args.init,
            "epochs": args.epochs,
        }, ckpt)
        print("wrote", ckpt)


if __name__ == "__main__":
    main()
