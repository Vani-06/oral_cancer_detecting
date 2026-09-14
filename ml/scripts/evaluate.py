"""
Evaluate the trained checkpoint on two DIFFERENT held-out sets, reported
separately -- never blended into one number:

1. The Kaggle test split (kaggle_split/test/) -- standard held-out accuracy,
   but this only tells you the model works on Kaggle's own image distribution.

2. The client's 99-image external validation set (client_validation/) -- real
   clinical photos from the client's own patients. This set is 98
   Non-Cancer / 1 Cancer (checked directly against the source spreadsheet), so
   it CANNOT measure cancer-detection sensitivity. What it measures is
   whether the model over-calls Cancer on real precancerous lesions (dysplasia,
   OSMF, PVL, hyperkeratosis) that were never confirmed malignant -- exactly
   the ambiguous cases most likely to trip up a model trained only on Kaggle's
   cleaner cancer/non-cancer split.

IMPORTANT: --client-eval-dir must point at data genuinely untouched by this
checkpoint's training run. Evaluating against client_validation/ after some
of those same images were folded into training (see
prepare_combined_training.py) would be leaked, dishonest data -- use
client_holdout/ for any checkpoint trained on the combined set.

Usage:
    .venv/Scripts/python.exe scripts/evaluate.py
    .venv/Scripts/python.exe scripts/evaluate.py --checkpoint artifacts/resnet50_oral_cancer_v2.pt --client-eval-dir data/client_holdout
"""

import argparse
import csv
from pathlib import Path

import torch
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from torchvision import transforms
from torchvision.models import resnet50

ML_DIR = Path(__file__).resolve().parent.parent
KAGGLE_TEST_DIR = ML_DIR / "data" / "kaggle_split" / "test"


def load_model(checkpoint_path: Path):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    tf = transforms.Compose(
        [
            transforms.Resize((checkpoint["img_size"], checkpoint["img_size"])),
            transforms.ToTensor(),
            transforms.Normalize(checkpoint["mean"], checkpoint["std"]),
        ]
    )
    return model, tf, checkpoint["class_to_idx"]


@torch.no_grad()
def predict_batch(model, tf, class_to_idx, image_label_pairs):
    """image_label_pairs: list of (PIL Image, true_label_str). Returns
    (y_true, y_pred, y_score) as 0/1 arrays, score = P(Cancer)."""
    cancer_idx = class_to_idx["Cancer"]
    y_true, y_pred, y_score = [], [], []

    for image, true_label in image_label_pairs:
        tensor = tf(image).unsqueeze(0)
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1)[0]
        pred_idx = int(probs.argmax().item())

        y_true.append(1 if true_label == "Cancer" else 0)
        y_pred.append(1 if pred_idx == cancer_idx else 0)
        y_score.append(float(probs[cancer_idx].item()))

    return y_true, y_pred, y_score


def report(name: str, y_true, y_pred, y_score, warn_on_single_class: bool = False):
    print(f"\n=== {name} ===")
    print(f"n = {len(y_true)}  (Cancer: {sum(y_true)}, Non-Cancer: {len(y_true) - sum(y_true)})")

    if warn_on_single_class and sum(y_true) <= 1:
        print(
            "NOTE: this set has 1 or 0 confirmed-cancer examples. Precision/recall/"
            "ROC-AUC for the Cancer class are not meaningful here -- reporting "
            "them anyway for completeness, but the number that matters is the "
            "Non-Cancer false-positive-avoidance rate below."
        )

    acc = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    print(f"Accuracy:  {acc:.3f}")
    print(f"Precision (Cancer): {precision:.3f}")
    print(f"Recall (Cancer):    {recall:.3f}")
    print(f"F1 (Cancer):        {f1:.3f}")

    try:
        auc = roc_auc_score(y_true, y_score)
        print(f"ROC-AUC:   {auc:.3f}")
    except ValueError:
        print("ROC-AUC:   undefined (only one class present in y_true)")

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    print("Confusion matrix [rows=true, cols=pred], order [Non-Cancer, Cancer]:")
    print(cm)

    false_cancer_calls = int(cm[0][1]) if cm.shape == (2, 2) else 0
    non_cancer_total = int(sum(1 for t in y_true if t == 0))
    if non_cancer_total:
        print(
            f"False-Cancer-call rate on Non-Cancer/precancerous images: "
            f"{false_cancer_calls}/{non_cancer_total} "
            f"({100 * false_cancer_calls / non_cancer_total:.1f}%)"
        )


def load_kaggle_test():
    pairs = []
    for label_dir in KAGGLE_TEST_DIR.iterdir():
        label = label_dir.name
        for f in label_dir.iterdir():
            pairs.append((Image.open(f).convert("RGB"), label))
    return pairs


def load_client_set(client_dir: Path):
    manifest_path = client_dir / "manifest.csv"
    pairs = []
    with manifest_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            image = Image.open(client_dir / row["filename"]).convert("RGB")
            pairs.append((image, row["label"]))
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint", type=Path,
        default=ML_DIR / "artifacts" / "resnet50_oral_cancer.pt",
    )
    parser.add_argument(
        "--client-eval-dir", type=Path,
        default=ML_DIR / "data" / "client_validation",
        help="Must be data NOT used in this checkpoint's training (see module docstring).",
    )
    args = parser.parse_args()

    if not args.checkpoint.is_file():
        print(f"No checkpoint found at {args.checkpoint}. Run train.py first.")
        return

    model, tf, class_to_idx = load_model(args.checkpoint)
    print(f"Evaluating checkpoint: {args.checkpoint}")

    if KAGGLE_TEST_DIR.is_dir():
        pairs = load_kaggle_test()
        y_true, y_pred, y_score = predict_batch(model, tf, class_to_idx, pairs)
        report("Kaggle test split (internal, same distribution as training)", y_true, y_pred, y_score)
    else:
        print(f"Skipping Kaggle test set -- not found at {KAGGLE_TEST_DIR}")

    if (args.client_eval_dir / "manifest.csv").is_file():
        pairs = load_client_set(args.client_eval_dir)
        y_true, y_pred, y_score = predict_batch(model, tf, class_to_idx, pairs)
        report(
            f"Client evaluation ({args.client_eval_dir.name}, real clinical photos)",
            y_true, y_pred, y_score, warn_on_single_class=True,
        )
    else:
        print(f"Skipping client eval set -- not found at {args.client_eval_dir}")


if __name__ == "__main__":
    main()
