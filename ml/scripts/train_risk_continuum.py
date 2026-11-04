"""
Pathology-ordered risk model (CONFIDENTIAL; private branch).

The binary model is told only "cancer or not", so a normal mouth, a benign
lesion and severe dysplasia are the same negative class -- and it confuses
lesions with cancer. This model learns the ordered ladder

    0 normal < 1 benign lesion < 2 mild < 3 moderate < 4 severe dysplasia < 5 cancer

with a rank-consistent ordinal head (CORAL: one shared score, five ordered
thresholds; P(level > k) = sigmoid(score - b_k)). P(cancer) = P(level > 4);
the expected level gives the dysplasia grade, from the same model.

Levels come from the corrected training split (case_split_fixed/train):
Kaggle Non-Cancer -> 0, relabelled_* (benign per the original source) -> 1,
client_* -> the biopsy grade in data/client_cases/manifest.csv, Cancer -> 5.

Selection: best validation cancer AUC. Evaluation (once): corrected test
split, benign-lesion test photos, client held-out patients (cancer flags
and grade), external healthy cheek / lichen planus -- compared with the
binary round-7 model at the same validation sensitivity.

Usage:
    .venv/Scripts/python.exe scripts/train_risk_continuum.py [--epochs 12]
"""

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from sklearn.metrics import cohen_kappa_score, roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stress_test as st  # noqa: E402
from train import _shortcut_edits  # noqa: E402

ML_DIR = Path(__file__).resolve().parent.parent
DATA = ML_DIR / "data"
LEVELS = ["normal", "benign", "mild", "moderate", "severe", "cancer"]
GRADE_LEVEL = {"mild_dysplasia": 2, "moderate_dysplasia": 3, "severe_dysplasia": 4}
MEAN, STD, SIZE = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225], 224


def client_grades():
    out = {}
    for r in csv.DictReader(open(DATA / "client_cases" / "manifest.csv")):
        if r["dx_group"] in GRADE_LEVEL:
            out[int(r["case_id"])] = GRADE_LEVEL[r["dx_group"]]
    return out


def level_of(path: Path, grades: dict[int, int]) -> int | None:
    if path.parent.name == "Cancer":
        return 5
    name = path.name
    if name.startswith("relabelled_"):
        return 1
    m = re.match(r"client_case(\d+)", name)
    if m:
        return grades.get(int(m.group(1)))  # None: no usable grade
    return 0


class Levelled(Dataset):
    def __init__(self, items, train: bool):
        self.items, self.train = items, train
        tail = [transforms.ToTensor(), transforms.Normalize(MEAN, STD)]
        self.plain = transforms.Compose([transforms.Resize((SIZE, SIZE)), *tail])
        aug = [transforms.RandomHorizontalFlip(), transforms.RandomRotation(10),
               transforms.ColorJitter(0.1, 0.1, 0.1), *tail]
        self.mild = transforms.Compose([transforms.RandomResizedCrop(SIZE, scale=(0.7, 1.0)), *aug])
        self.zoom = transforms.Compose([transforms.RandomResizedCrop(SIZE, scale=(0.15, 0.6)), *aug])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, level = self.items[i]
        with Image.open(path) as im:
            image = ImageOps.exif_transpose(im).convert("RGB")
        if not self.train:
            return self.plain(image), level
        image = _shortcut_edits(image)
        # Close-up crops only of normal mouths: a crop of a lesion might cut it out.
        tf = self.zoom if level == 0 and random.random() < 0.5 else self.mild
        return tf(image), level


class OrdinalResNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        for p in self.backbone.parameters():
            p.requires_grad = False
        for p in self.backbone.layer4.parameters():
            p.requires_grad = True
        self.backbone.fc = nn.Linear(2048, 1, bias=False)
        self.thresholds = nn.Parameter(torch.linspace(-2, 2, len(LEVELS) - 1))

    def forward(self, x):
        score = self.backbone(x)  # B x 1
        return score - self.thresholds[None, :]  # B x 5 logits for P(level > k)


def ordinal_targets(levels):
    k = torch.arange(len(LEVELS) - 1)
    return (levels[:, None] > k[None, :]).float()


@torch.no_grad()
def predict(model, paths):
    model.eval()
    ds = Levelled([(p, 0) for p in paths], train=False)
    out = [torch.sigmoid(model(x)) for x, _ in DataLoader(ds, batch_size=32)]
    return torch.cat(out).numpy()  # N x 5: P(level > k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    grades = client_grades()

    def items(split):
        paths = sorted(p for p in (DATA / "case_split_fixed" / split).rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
        return [(p, lv) for p in paths if (lv := level_of(p, grades)) is not None]

    train_items, val_items = items("train"), items("val")
    print("train levels:", dict(zip(LEVELS, np.bincount([lv for _, lv in train_items], minlength=6).tolist())), flush=True)

    model = OrdinalResNet()
    opt = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=args.lr)
    loader = DataLoader(Levelled(train_items, train=True), batch_size=16, shuffle=True)
    val_paths = [p for p, _ in val_items]
    val_cancer = np.array([lv == 5 for _, lv in val_items])
    best, ckpt = -1.0, ML_DIR / "artifacts" / "resnet50_risk_continuum_v1.pt"
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for x, lv in loader:
            opt.zero_grad()
            loss = nn.functional.binary_cross_entropy_with_logits(model(x), ordinal_targets(lv))
            loss.backward()
            opt.step()
            total += loss.item() * len(lv)
        auc = roc_auc_score(val_cancer, predict(model, val_paths)[:, 4])
        print(f"epoch {epoch:2d}/{args.epochs} | loss {total / len(train_items):.4f} | val cancer AUC {auc:.4f}", flush=True)
        if auc > best:
            best = auc
            torch.save({"state_dict": model.state_dict(), "levels": LEVELS, "img_size": SIZE,
                        "mean": MEAN, "std": STD, "epoch": epoch, "val_auc": auc}, ckpt)
    print(f"best validation cancer AUC {best:.4f}; wrote {ckpt}", flush=True)
    model.load_state_dict(torch.load(ckpt, weights_only=False)["state_dict"])
    evaluate(model, val_items, grades)


def evaluate(model, val_items, grades):
    binary = st.load_model(ML_DIR / "artifacts" / "resnet50_oral_cancer_v7.pt")

    def both(paths):
        ims = [st.open_rgb(p) for p in paths]
        return predict(model, paths), st.run(*binary, ims)[0]

    val_paths = [p for p, _ in val_items]
    val_y = np.array([lv == 5 for _, lv in val_items])
    test_paths = sorted(p for p in (DATA / "kaggle_split_fixed" / "test").rglob("*") if p.suffix.lower() in st.IMAGE_EXTS)
    test_y = np.array([p.parent.name == "Cancer" for p in test_paths])
    benign_test = np.array([p.name.startswith("relabelled_") for p in test_paths])
    hold_rows = list(csv.DictReader(open(DATA / "case_split" / "holdout" / "manifest.csv")))
    hold_paths = [DATA / "case_split" / "holdout" / r["filename"] for r in hold_rows]
    hold_level = np.array([GRADE_LEVEL.get(r["dx_group"], -1) for r in hold_rows])
    ext = DATA / "external" / "olp_synthesis" / "extracted" / "data"
    cheek_paths = sorted((ext / "negative").glob("*"))
    olp_paths = sorted((ext / "lesion_img").glob("*"))

    (vo, vb), (to, tb) = both(val_paths), both(test_paths)
    (ho, hb), (co, cb), (oo, ob) = both(hold_paths), both(cheek_paths), both(olp_paths)
    # Operating point: the binary model's validation sensitivity at 0.5.
    target = (vb[val_y] >= 0.5).mean()
    cut = np.sort(vo[val_y, 4])[::-1][int(np.ceil(target * val_y.sum())) - 1]
    rows = {}
    for name, val_s, test_s, hold_s, cheek_s, olp_s, t in [
        ("binary_round7", vb, tb, hb, cb, ob, 0.5),
        ("risk_continuum", vo[:, 4], to[:, 4], ho[:, 4], co[:, 4], oo[:, 4], cut),
    ]:
        f = test_s >= t
        rows[name] = {
            "val_auc": float(roc_auc_score(val_y, val_s)), "test_auc": float(roc_auc_score(test_y, test_s)),
            "test_sensitivity": float(f[test_y].mean()), "test_specificity": float((~f[~test_y]).mean()),
            "test_benign_lesions_flagged": f"{int(f[benign_test].sum())}/{int(benign_test.sum())}",
            "client_dysplasia_flagged": float((hold_s >= t).mean()),
            "external_healthy_cheek_flagged": f"{int((cheek_s >= t).sum())}/{len(cheek_s)}",
            "external_lichen_planus_flagged": f"{int((olp_s >= t).sum())}/{len(olp_s)}",
        }
    # Grade from the same model: expected level among dysplasia patients, mapped to 2..4.
    graded = hold_level >= 2
    expected = ho.sum(1)  # E[level] = sum_k P(level > k)
    grade_pred = np.clip(np.rint(expected), 2, 4)[graded]
    rows["risk_continuum"]["client_holdout_grade_accuracy"] = float((grade_pred == hold_level[graded]).mean())
    rows["risk_continuum"]["client_holdout_grade_kappa"] = float(cohen_kappa_score(hold_level[graded], grade_pred, weights="quadratic"))
    rows["majority_grade_baseline_accuracy"] = float(np.bincount(hold_level[graded]).max() / graded.sum())
    print(json.dumps(rows, indent=2))
    (ML_DIR / "artifacts" / "risk_continuum_eval.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
