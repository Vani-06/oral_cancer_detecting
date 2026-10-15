"""
Correct Kaggle labels using the dataset they were copied from.

313 of the 323 photos in the Mendeley "Oral Images Dataset" (Chandrashekar
H S et al., Malnad College of Engineering; DOI 10.17632/mhjyrn35p4.2, CC BY
4.0; collected with doctors in Karnataka) also appear in the Kaggle oral
cancer dataset. Every disagreement goes one way: photos the original source
files as *benign lesions* sit in Kaggle's Cancer folder -- 52 of the round-4
model's training "cancers", 8 validation and 12 test photos. A model trained
on that learns "benign lesion close-up = cancer", which matches the false
positives seen on textbook photos.

This copies data/case_split and data/kaggle_split/test to *_fixed folders
with those photos moved to Non-Cancer, and writes the list of changes to
data/external/relabelled.csv. Matches come from
data/external/label_crosscheck.csv (24x24 greyscale thumbnail cosine
similarity > 0.97; all matches were >= 0.999).

Usage:
    .venv/Scripts/python.exe scripts/fix_labels.py
"""

import csv
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def main():
    relabel = {
        Path(r["our_path"]).as_posix()
        for r in csv.DictReader(open(DATA / "external" / "label_crosscheck.csv"))
        if r["our_label"] == "Cancer" and r["mendeley_label"] == "Non-Cancer"
    }
    changes = []
    for src_root, dst_root, splits in [
        (DATA / "case_split", DATA / "case_split_fixed", ["train", "val", "holdout"]),
        (DATA / "kaggle_split", DATA / "kaggle_split_fixed", ["test"]),
    ]:
        shutil.rmtree(dst_root, ignore_errors=True)
        for split in splits:
            for p in sorted((src_root / split).rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(src_root)
                key = (Path("data") / src_root.name / rel).as_posix()
                if key in relabel:
                    # Kaggle numbers each class folder separately, so keep the moved
                    # file from overwriting a Non-Cancer photo of the same name.
                    rel = Path(rel.parts[0], "Non-Cancer", "relabelled_" + rel.name)
                    changes.append([key, "Cancer", "Non-Cancer"])
                dst = dst_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
    with open(DATA / "external" / "relabelled.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "old_label", "new_label"])
        w.writerows(changes)
    print(f"relabelled {len(changes)} photos Cancer -> Non-Cancer")
    for root in ["case_split_fixed/train", "case_split_fixed/val", "kaggle_split_fixed/test"]:
        counts = {c.name: len(list(c.iterdir())) for c in sorted((DATA / root).iterdir()) if c.is_dir()}
        print(f"  {root}: {counts}")


if __name__ == "__main__":
    main()
