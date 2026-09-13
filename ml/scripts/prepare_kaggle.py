"""
Build a clean train/val/test split from the downloaded Kaggle oral cancer
dataset ("Oral cancer Dataset 2.0" -- 500 CANCER / 450 NON CANCER images,
matching the counts in the project's progress report).

This does more than copy files into folders: the raw download has real
duplicate and near-duplicate images (checked directly -- 8% of CANCER files
are byte-identical duplicates, plus further near-duplicates at perceptual
hamming distance <=2, e.g. recompressed or trivially cropped reposts of the
same source photo). Left alone, a naive random split would let the same
underlying photo land in both train and test, which inflates test accuracy
without the model having learned anything more general. Every image is
clustered (union-find over exact + near-duplicate hashes) before splitting,
and the split is done per cluster so no duplicate can ever cross a boundary.

Usage:
    .venv/Scripts/python.exe scripts/prepare_kaggle.py

Output:
    ml/data/kaggle_split/{train,val,test}/{Cancer,Non-Cancer}/*.jpeg
    ml/data/kaggle_split/manifest.csv  (path, label, split, dedup_cluster)
"""

import csv
import random
from pathlib import Path

from PIL import Image

RAW_BASE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "kaggle_raw"
    / "Oral cancer Dataset 2.0"
    / "OC Dataset kaggle new"
)
OUT_BASE = Path(__file__).resolve().parent.parent / "data" / "kaggle_split"

CLASS_DIRS = {"CANCER": "Cancer", "NON CANCER": "Non-Cancer"}
NEAR_DUP_HAMMING_THRESHOLD = 2
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
RANDOM_SEED = 42


def ahash(path: Path, size: int = 8) -> int:
    im = Image.open(path).convert("L").resize((size, size))
    pixels = list(im.getdata())
    avg = sum(pixels) / len(pixels)
    return int("".join("1" if p > avg else "0" for p in pixels), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_duplicates(files: list[Path]) -> list[list[Path]]:
    """Group exact and near-duplicate images. O(n^2) hamming comparisons,
    fine at this dataset's size (under 1000 images)."""
    hashes = [(f, ahash(f)) for f in files]
    uf = UnionFind(files)
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            if hamming(hashes[i][1], hashes[j][1]) <= NEAR_DUP_HAMMING_THRESHOLD:
                uf.union(hashes[i][0], hashes[j][0])

    clusters: dict[Path, list[Path]] = {}
    for f in files:
        root = uf.find(f)
        clusters.setdefault(root, []).append(f)
    return list(clusters.values())


def assign_splits(n_clusters: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    labels = (
        ["train"] * round(n_clusters * SPLIT_RATIOS["train"])
        + ["val"] * round(n_clusters * SPLIT_RATIOS["val"])
    )
    labels += ["test"] * (n_clusters - len(labels))
    rng.shuffle(labels)
    return labels


def main() -> None:
    if not RAW_BASE.is_dir():
        print(f"Expected raw dataset at {RAW_BASE} -- not found.")
        print("Run: kaggle datasets download -d zaidpy/oral-cancer-dataset -p data/kaggle_raw --unzip")
        return

    manifest_rows = []

    for raw_name, label in CLASS_DIRS.items():
        files = sorted((RAW_BASE / raw_name).iterdir())
        clusters = cluster_duplicates(files)
        clusters.sort(key=lambda c: c[0].name)  # deterministic order before shuffle

        splits = assign_splits(len(clusters), seed=RANDOM_SEED)

        n_dupe_clusters = sum(1 for c in clusters if len(c) > 1)
        n_dupe_files = sum(len(c) for c in clusters if len(c) > 1)
        print(
            f"{raw_name}: {len(files)} files -> {len(clusters)} unique clusters "
            f"({n_dupe_clusters} clusters absorbed {n_dupe_files} duplicate/near-duplicate files)"
        )

        for cluster, split in zip(clusters, splits):
            # Keep only the canonical (first) file per cluster -- duplicates
            # are dropped entirely, not just kept out of other splits, so the
            # model doesn't see the same photo weighted multiple times either.
            canonical = cluster[0]
            out_dir = OUT_BASE / split / label
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / canonical.name
            out_path.write_bytes(canonical.read_bytes())
            manifest_rows.append(
                {
                    "path": str(out_path.relative_to(OUT_BASE)),
                    "label": label,
                    "split": split,
                    "cluster_size": len(cluster),
                }
            )

    manifest_path = OUT_BASE / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "label", "split", "cluster_size"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nWrote {len(manifest_rows)} deduplicated images to {OUT_BASE}")
    for split in ["train", "val", "test"]:
        counts = {
            label: sum(1 for r in manifest_rows if r["split"] == split and r["label"] == label)
            for label in CLASS_DIRS.values()
        }
        print(f"  {split}: {counts}")


if __name__ == "__main__":
    main()
