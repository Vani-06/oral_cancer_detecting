"""
Fold the client's own clinical photos into training, not just validation --
the standard fix for the domain-shift failure documented in
ml/artifacts/model_card.md (round 1: Kaggle-only training reached 92.6%
Kaggle-test accuracy but an 85.7% false-Cancer-call rate on real client
photos).

Honesty constraint that shapes this whole script: the client set has exactly
ONE confirmed-cancer image. Whatever split is chosen, either that image is
used for training (and cancer-detection sensitivity in this photo domain
stays fundamentally unverified) or it's held out (and training sees zero
client-domain positive examples). This script uses it in training, because a
single held-out positive proves nothing statistically anyway -- but the
resulting model's cancer-detection sensitivity on real photos must still be
reported as unverified, not assumed fixed.

The 98 Non-Cancer client images -- where the actual measurable problem is --
get a real three-way split so the fix can be honestly checked:
    58 -> combined_train  (train)
    20 -> combined_val    (mixed into validation, informs checkpoint choice)
    20 -> client_holdout  (never touched until final evaluation)

Usage:
    .venv/Scripts/python.exe scripts/prepare_combined_training.py

Output:
    ml/data/combined_train/{Cancer,Non-Cancer}/   (kaggle train + client split)
    ml/data/combined_val/{Cancer,Non-Cancer}/     (kaggle val + client split)
    ml/data/client_holdout/manifest.csv + images  (untouched until eval)
"""

import csv
import random
import shutil
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent.parent
KAGGLE_SPLIT = ML_DIR / "data" / "kaggle_split"
CLIENT_VAL = ML_DIR / "data" / "client_validation"
COMBINED_TRAIN = ML_DIR / "data" / "combined_train"
COMBINED_VAL = ML_DIR / "data" / "combined_val"
CLIENT_HOLDOUT = ML_DIR / "data" / "client_holdout"

RANDOM_SEED = 42
CLIENT_NONCANCER_SPLIT = {"train": 58, "val": 20, "holdout": 20}


def copy_tree_into(src_split_dir: Path, dest_dir: Path) -> None:
    for label_dir in src_split_dir.iterdir():
        out_dir = dest_dir / label_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in label_dir.iterdir():
            shutil.copy(f, out_dir / f.name)


def main() -> None:
    for d in [COMBINED_TRAIN, COMBINED_VAL, CLIENT_HOLDOUT]:
        if d.exists():
            shutil.rmtree(d)

    print("Copying Kaggle train -> combined_train, Kaggle val -> combined_val")
    copy_tree_into(KAGGLE_SPLIT / "train", COMBINED_TRAIN)
    copy_tree_into(KAGGLE_SPLIT / "val", COMBINED_VAL)

    manifest_path = CLIENT_VAL / "manifest.csv"
    with manifest_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    cancer_rows = [r for r in rows if r["label"] == "Cancer"]
    noncancer_rows = [r for r in rows if r["label"] == "Non-Cancer"]
    print(f"Client set: {len(cancer_rows)} Cancer, {len(noncancer_rows)} Non-Cancer")

    rng = random.Random(RANDOM_SEED)
    rng.shuffle(noncancer_rows)

    n_train = CLIENT_NONCANCER_SPLIT["train"]
    n_val = CLIENT_NONCANCER_SPLIT["val"]
    train_rows = noncancer_rows[:n_train]
    val_rows = noncancer_rows[n_train:n_train + n_val]
    holdout_rows = noncancer_rows[n_train + n_val:]

    # The single Cancer image goes to training -- see module docstring for why.
    for row in cancer_rows:
        out_dir = COMBINED_TRAIN / "Cancer"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(CLIENT_VAL / row["filename"], out_dir / f"client_{row['filename']}")

    for row in train_rows:
        out_dir = COMBINED_TRAIN / "Non-Cancer"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(CLIENT_VAL / row["filename"], out_dir / f"client_{row['filename']}")

    for row in val_rows:
        out_dir = COMBINED_VAL / "Non-Cancer"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(CLIENT_VAL / row["filename"], out_dir / f"client_{row['filename']}")

    CLIENT_HOLDOUT.mkdir(parents=True, exist_ok=True)
    holdout_manifest = []
    for row in holdout_rows:
        shutil.copy(CLIENT_VAL / row["filename"], CLIENT_HOLDOUT / row["filename"])
        holdout_manifest.append(row)
    with (CLIENT_HOLDOUT / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "label"])
        writer.writeheader()
        writer.writerows(holdout_manifest)

    def count(d: Path) -> dict:
        return {p.name: len(list(p.iterdir())) for p in d.iterdir() if p.is_dir()}

    print(f"\ncombined_train: {count(COMBINED_TRAIN)}")
    print(f"combined_val:   {count(COMBINED_VAL)}")
    print(f"client_holdout: {len(holdout_manifest)} images (all Non-Cancer, untouched until final eval)")


if __name__ == "__main__":
    main()
