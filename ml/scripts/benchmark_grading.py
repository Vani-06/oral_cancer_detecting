"""
Benchmark dysplasia grading (mild / moderate / severe) from the photo, the
patient's case-sheet details, and both together.

Inputs per graded patient (99 cases from data/client_cases):
- photo: ImageNet ResNet-50 features, averaged over the patient's photos
  and a mirrored copy of each;
- details: age, sex, habits (pan / gutkha-tobacco / smoking / alcohol),
  habit years, diabetes, hypertension, and lesion site + findings taken
  from the clinical notes by keyword (pain, ulcer, growth, white or red
  patch, fibrous bands, restricted opening, palpable). Grade words
  ("dysplasia", "mild", ... -- 8 notes contain them, written after the
  biopsy) are never read. FieldValue, the diagnosis column, is the label.

Evaluation: patient-grouped, grade-stratified 5-fold CV repeated over 10
seeds; every metric is per patient. Because several setups are compared on
just 99 patients, the best one is also re-run with shuffled grades 30 times
to show what that score looks like by luck.

Usage:
    .venv/Scripts/python.exe scripts/benchmark_grading.py <treatment.xlsx>
"""

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torchvision import transforms
from torchvision.models import ResNet50_Weights, resnet50

ML_DIR = Path(__file__).resolve().parent.parent
CASES_DIR = ML_DIR / "data" / "client_cases"
GRADES = ["mild_dysplasia", "moderate_dysplasia", "severe_dysplasia"]
COLS = {"age": 2, "sex": 3, "habits": 7, "duration": 8, "medical": 9, "notes": 10}

# Keyword -> feature. Mirrors fields the app's patient form collects
# (sex, tobacco type, betel quid, alcohol, years, lesion site, pain) plus
# findings a clinician writes in the notes.
HABIT_WORDS = {
    "pan": r"\bpan\b|betel|areca|supari|paan",
    "chewed_tobacco": r"gutk|gutka|gutkha|khaini|tobacco|zarda|mawa",
    "smoking": r"smok|bidi|beedi|cigar",
    "alcohol": r"alcohol",
}
NOTE_WORDS = {
    "site_buccal": r"buccal|cheek",
    "site_tongue": r"tongue",
    "site_gingiva": r"gingiv|\bgum",
    "site_palate": r"palat",
    "site_lip": r"\blip",
    "site_floor": r"floor of (the )?mouth",
    "pain": r"\bpain|burning",
    "ulcer": r"ulcer",
    "growth": r"growth|prolifer|mass\b",
    "white_patch": r"white",
    "red_patch": r"\bred\b|erythro",
    "bands": r"\bband|fibro|blanch",
    "restricted_opening": r"opening|trismus",
    "palpable": r"palpab|indurat",
}


def years(text: str) -> float:
    m = re.search(r"(\d+(\.\d+)?)", text)
    if not m:
        return 0.0
    v = float(m.group(1))
    return v / 12 if "month" in text else v


def case_details(xlsx: Path, case_ids: list[int]) -> tuple[np.ndarray, list[str]]:
    import openpyxl

    ws = openpyxl.load_workbook(xlsx, read_only=True, data_only=True).active
    rows = {i + 2: r for i, r in enumerate(ws.iter_rows(min_row=2, max_row=200, values_only=True))}
    names = ["age", "male", *HABIT_WORDS, "habit_years", "diabetes", "hypertension", *NOTE_WORDS]
    out = []
    for case in case_ids:
        r = rows[case + 1]  # case N is spreadsheet row N+1 (see prepare_client_cases.py)
        txt = {k: str(r[i] or "").lower() for k, i in COLS.items()}
        feats = [float(r[COLS["age"]] or 0), float(txt["sex"].strip().startswith("m"))]
        feats += [float(bool(re.search(p, txt["habits"]))) for p in HABIT_WORDS.values()]
        feats.append(years(txt["duration"]))
        feats += [float("diabet" in txt["medical"]), float("hypertens" in txt["medical"])]
        feats += [float(bool(re.search(p, txt["notes"]))) for p in NOTE_WORDS.values()]
        out.append(feats)
    return np.array(out), names


@torch.no_grad()
def photo_features(paths_by_case: dict[int, list[Path]], case_ids: list[int]) -> np.ndarray:
    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2).eval()
    model.fc = torch.nn.Identity()
    tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    out = []
    for case in case_ids:
        ims = []
        for p in paths_by_case[case]:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
            ims += [tf(im), tf(ImageOps.mirror(im))]
        f = model(torch.stack(ims))
        f = f / f.norm(dim=1, keepdim=True)
        out.append(f.mean(0).numpy())
    return np.array(out)


def make_model(c: float):
    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=5000, class_weight="balanced"))


def cv_predict(X, y, c, seed):
    pred = np.zeros_like(y)
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
        pred[te] = make_model(c).fit(X[tr], y[tr]).predict(X[te])
    return pred


def score(X, y, c, seeds=range(10)):
    accs, baccs, kappas = [], [], []
    for s in seeds:
        p = cv_predict(X, y, c, s)
        accs.append(np.mean(p == y))
        baccs.append(np.mean([np.mean(p[y == k] == k) for k in range(3)]))
        kappas.append(cohen_kappa_score(y, p, weights="quadratic"))
    return {"accuracy": float(np.mean(accs)), "balanced_accuracy": float(np.mean(baccs)),
            "quadratic_kappa": float(np.mean(kappas)), "kappa_sd_over_seeds": float(np.std(kappas))}


def main():
    xlsx = Path(sys.argv[1])
    rows = [r for r in csv.DictReader(open(CASES_DIR / "manifest.csv")) if r["dx_group"] in GRADES]
    grade_of, paths_by_case = {}, {}
    for r in rows:
        case = int(r["case_id"])
        grade_of[case] = GRADES.index(r["dx_group"])
        paths_by_case.setdefault(case, []).append(CASES_DIR / r["filename"])
    case_ids = sorted(grade_of)
    y = np.array([grade_of[c] for c in case_ids])
    print(f"{len(case_ids)} patients, per grade {np.bincount(y).tolist()}", flush=True)

    details, names = case_details(xlsx, case_ids)
    photo = photo_features(paths_by_case, case_ids)
    np.savez(ML_DIR / "artifacts" / "grading_benchmark_features.npz", details=details, photo=photo, y=y,
             case_ids=np.array(case_ids), names=np.array(names))
    sets = {"details only": details, "photo only": photo, "photo + details": np.hstack([photo, details])}

    results = {"majority_baseline_accuracy": float(np.bincount(y).max() / len(y))}
    print(f"always 'moderate': accuracy {results['majority_baseline_accuracy']:.3f}, kappa 0")
    best = None
    for name, X in sets.items():
        for c in [0.01, 0.1, 1.0]:
            r = score(X, y, c)
            results[f"{name} C={c}"] = r
            print(f"{name:16s} C={c:<5} acc {r['accuracy']:.3f}  balanced {r['balanced_accuracy']:.3f}  "
                  f"kappa {r['quadratic_kappa']:.3f} (+/-{r['kappa_sd_over_seeds']:.3f})", flush=True)
            if best is None or r["quadratic_kappa"] > best[2]["quadratic_kappa"]:
                best = (name, c, r)

    name, c, r = best
    rng = np.random.default_rng(0)
    null = [score(sets[name], rng.permutation(y), c, seeds=range(3))["quadratic_kappa"] for _ in range(30)]
    results["best"] = {"setup": name, "C": c, **r}
    results["shuffled_grades_kappa"] = {"mean": float(np.mean(null)), "max": float(np.max(null)),
                                        "share_at_or_above_best": float(np.mean(np.array(null) >= r["quadratic_kappa"]))}
    print(f"\nbest: {name} C={c} kappa {r['quadratic_kappa']:.3f}; shuffled grades: mean {np.mean(null):.3f}, "
          f"max {np.max(null):.3f}, share >= best {results['shuffled_grades_kappa']['share_at_or_above_best']:.2f}")

    if "details" in name:
        coef = make_model(c).fit(sets["details only"], y)[-1].coef_
        order = np.argsort(-np.abs(coef[2] - coef[0]))[:10]
        print("details pushing towards severe (+) vs mild (-):",
              [(names[i], round(float(coef[2][i] - coef[0][i]), 2)) for i in order])
    (ML_DIR / "artifacts" / "grading_benchmark.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
