"""
How much do common evaluation shortcuts inflate reported accuracy on the
public Kaggle oral cancer dataset (v2.0, 950 photos)?

Same simple classifier throughout -- frozen ImageNet ResNet-50 features +
logistic regression -- so only the evaluation protocol changes:

  A. "as commonly done": raw 950 photos (duplicates kept), original labels,
     every photo also added as 3 augmented copies (flip, rotations) BEFORE a
     random 80/20 split, so copies of a test photo sit in training
  B. raw photos, original labels, random split (duplicates can straddle it)
  C. duplicates grouped (never split across train/test), original labels
  D. C + labels corrected against the original Mendeley source
     (benign lesions that Kaggle files as Cancer -> Non-Cancer)

Each protocol is repeated over 5 random splits; mean and range reported.

Usage:
    .venv/Scripts/python.exe scripts/leakage_experiment.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

ML_DIR = Path(__file__).resolve().parent.parent
RAW = ML_DIR / "data" / "kaggle_raw" / "Oral cancer Dataset 2.0"
MENDELEY_BENIGN = ML_DIR / "data" / "external" / "mendeley_oral_images" / "benign"
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def thumb(im):
    a = np.asarray(im.convert("L").resize((24, 24)), dtype=np.float32)
    a = a - a.mean()
    return a.ravel() / (np.linalg.norm(a) + 1e-6)


def groups_by_similarity(thumbs, thr=0.97):
    """Union-find over near-duplicate pairs."""
    parent = list(range(len(thumbs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    S = thumbs @ thumbs.T
    for i, j in zip(*np.where(np.triu(S, 1) > thr)):
        parent[find(i)] = find(j)
    return np.array([find(i) for i in range(len(thumbs))])


@torch.no_grad()
def embed(model, tf, images):
    out = []
    for i in range(0, len(images), 32):
        out.append(model(torch.stack([tf(im) for im in images[i:i + 32]])))
    f = torch.cat(out).numpy()
    return f / np.linalg.norm(f, axis=1, keepdims=True)


def evaluate(X, y, groups, seeds=5, augmented=None):
    accs, aucs = [], []
    for seed in range(seeds):
        if augmented is not None:
            # Augment first, then split rows at random: copies leak across.
            Xa, ya = augmented
            idx = np.random.default_rng(seed).permutation(len(ya))
            cut = int(0.8 * len(ya))
            tr, te = idx[:cut], idx[cut:]
            if ya.dtype != bool:
                raise ValueError("labels must be boolean")
            clf = LogisticRegression(C=1.0, max_iter=3000).fit(Xa[tr], ya[tr])
            p = clf.predict_proba(Xa[te])[:, 1]
            accs.append(accuracy_score(ya[te], p >= 0.5))
            aucs.append(roc_auc_score(ya[te], p))
            continue
        tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=seed).split(X, y, groups))
        clf = LogisticRegression(C=1.0, max_iter=3000).fit(X[tr], y[tr])
        p = clf.predict_proba(X[te])[:, 1]
        accs.append(accuracy_score(y[te], p >= 0.5))
        aucs.append(roc_auc_score(y[te], p))
    r = lambda v: {"mean": float(np.mean(v)), "sd": float(np.std(v, ddof=1)), "min": float(np.min(v)), "max": float(np.max(v))}  # noqa: E731
    return {"accuracy": r(accs), "roc_auc": r(aucs)}


def main():
    paths = sorted(p for p in RAW.rglob("*") if p.suffix.lower() in EXTS)
    images = []
    for p in paths:
        with Image.open(p) as im:
            images.append(ImageOps.exif_transpose(im).convert("RGB"))
    y = np.array([p.parent.name.upper() == "CANCER" for p in paths])
    th = np.stack([thumb(im) for im in images])
    dup_groups = groups_by_similarity(th)
    benign = np.stack([thumb(Image.open(p).convert("RGB")) for p in sorted(MENDELEY_BENIGN.iterdir())])
    relabel = y & ((th @ benign.T).max(1) > 0.97)
    y_fixed = y & ~relabel
    print(f"{len(y)} photos, {y.sum()} labelled Cancer; {len(set(dup_groups))} distinct after grouping duplicates; "
          f"{relabel.sum()} 'Cancer' photos are benign lesions in the original source", flush=True)

    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2).eval()
    model.fc = torch.nn.Identity()
    tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    X = embed(model, tf, images)
    aug_images = [f(im) for im in images for f in (lambda i: i, ImageOps.mirror,
                                                     lambda i: i.rotate(90, expand=True), lambda i: i.rotate(180))]
    Xa = embed(model, tf, aug_images)
    ya = np.repeat(y, 4)

    singletons = np.arange(len(y))
    out = {
        "A_augment_then_random_split_original_labels": evaluate(X, y, singletons, augmented=(Xa, ya)),
        "B_random_split_duplicates_kept_original_labels": evaluate(X, y, singletons),
        "C_duplicates_grouped_original_labels": evaluate(X, y, dup_groups),
        "D_duplicates_grouped_corrected_labels": evaluate(X, y_fixed, dup_groups),
        # One factor at a time, on the same 5 split seeds (review item 34):
        "E_augment_then_random_split_corrected_labels": evaluate(X, y_fixed, singletons, augmented=(Xa, np.repeat(y_fixed, 4))),
        "F_random_split_duplicates_kept_corrected_labels": evaluate(X, y_fixed, singletons),
        "photos": int(len(y)), "distinct_after_dedup": int(len(set(dup_groups))),
        "benign_labelled_cancer": int(relabel.sum()),
    }
    for k, v in out.items():
        if isinstance(v, dict):
            print(f"{k:50s} accuracy {v['accuracy']['mean']:.3f} (SD {v['accuracy']['sd']:.3f})  "
                  f"AUC {v['roc_auc']['mean']:.3f} (SD {v['roc_auc']['sd']:.3f})")
    (ML_DIR / "artifacts" / "leakage_experiment.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
