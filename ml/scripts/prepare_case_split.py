"""
Case-level train/val/holdout split over the full client case set
(prepare_client_cases.py), combined with the Kaggle split.

Reuses round 2's exact patient assignment (prepare_combined_training.py:
seeded shuffle of the 98 Non-Cancer spreadsheet photos -> 58 train / 20 val /
20 holdout) so a model trained here can be compared against round 2 on the
SAME 20 held-out patients. The difference is that every split now carries
all photos of each patient (spreadsheet + verified folder photo), and no
patient appears in more than one split.

Cases not in round 2 at all (case 51 has no spreadsheet photo, so round 2
never saw it) go to training. The single carcinoma case also goes to
training, as in round 2 -- a held-out sample of one proves nothing.

Usage:
    .venv/Scripts/python.exe scripts/prepare_case_split.py

Output (ImageFolder layout for train.py, plus a case-level holdout):
    ml/data/case_split/train/{Cancer,Non-Cancer}/
    ml/data/case_split/val/{Cancer,Non-Cancer}/
    ml/data/case_split/holdout/manifest.csv + images
"""

import csv
import random
import shutil
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent.parent
KAGGLE = ML_DIR / "data" / "kaggle_split"
CLIENT_VALIDATION = ML_DIR / "data" / "client_validation"
CLIENT_CASES = ML_DIR / "data" / "client_cases"
OUT = ML_DIR / "data" / "case_split"

# Rows of the treatment sheet that have an embedded clinical photo, in the
# order prepare_client_validation.py numbered them val_001...val_099. Row 52
# has no embedded clinical photo. Case id = row - 1.
SHEET_ROWS_WITH_PHOTO = [r for r in range(2, 102) if r != 52]

ROUND2_SEED = 42
ROUND2_SPLIT = (58, 20, 20)


def round2_case_assignment() -> tuple[set[int], set[int], set[int]]:
    with (CLIENT_VALIDATION / "manifest.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    noncancer = [r for r in rows if r["label"] == "Non-Cancer"]
    random.Random(ROUND2_SEED).shuffle(noncancer)

    def case_of(filename: str) -> int:
        index = int(filename.removeprefix("val_").removesuffix(".jpg"))
        return SHEET_ROWS_WITH_PHOTO[index - 1] - 1

    n_train, n_val, _ = ROUND2_SPLIT
    train = {case_of(r["filename"]) for r in noncancer[:n_train]}
    val = {case_of(r["filename"]) for r in noncancer[n_train:n_train + n_val]}
    holdout = {case_of(r["filename"]) for r in noncancer[n_train + n_val:]}
    return train, val, holdout


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)

    for split in ("train", "val"):
        for label_dir in (KAGGLE / split).iterdir():
            dest = OUT / split / label_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            for f in label_dir.iterdir():
                shutil.copy(f, dest / f.name)

    _, val_cases, holdout_cases = round2_case_assignment()

    with (CLIENT_CASES / "manifest.csv").open(newline="", encoding="utf-8") as f:
        photos = list(csv.DictReader(f))

    holdout_rows = []
    (OUT / "holdout").mkdir(parents=True, exist_ok=True)
    for p in photos:
        case = int(p["case_id"])
        src = CLIENT_CASES / p["filename"]
        if case in holdout_cases:
            shutil.copy(src, OUT / "holdout" / p["filename"])
            holdout_rows.append(p)
            continue
        split = "val" if case in val_cases else "train"
        dest = OUT / split / p["label"]
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest / f"client_{p['filename']}")

    with (OUT / "holdout" / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(photos[0].keys()))
        w.writeheader()
        w.writerows(holdout_rows)

    def count(split: str) -> dict:
        d = OUT / split
        return {
            p.name: (len(list(p.iterdir())), len(list(p.glob("client_*"))))
            for p in d.iterdir() if p.is_dir()
        }

    print("train (total, of which client):", count("train"))
    print("val   (total, of which client):", count("val"))
    print(f"holdout: {len(holdout_rows)} photos from {len(holdout_cases)} cases "
          f"(same patients round 2 held out)")
    leak = (holdout_cases & val_cases)
    assert not leak, f"case overlap between holdout and val: {leak}"


if __name__ == "__main__":
    main()
