"""
Build a 100-photo demonstration set with known answers: 25 each of no
dysplasia, mild, moderate and severe dysplasia.

Every candidate is run through the app's own pipeline (photo check, quality
check, cancer triage, grading), and all results are written to
artifacts/demo_candidates.csv. The set is then chosen and copied to --out
with an answer key.

Truth: dysplasia grades are the client's histopathology diagnoses
(data/client_cases/manifest.csv); "no dysplasia" photos are healthy mouths
from the public Kaggle set (Non-Cancer, not relabelled benign lesions).

IMPORTANT, and written into the answer key: with --prefer-correct the photos
are chosen because the app answers them correctly, and the deployed grading
model was trained on most of the client photos. Such a set shows the app
working; it is NOT a measure of accuracy (held-out grading accuracy is
about 41-45%).

Run with the backend environment and the app's model settings:
    MODEL_PATH=... GRADING_MODEL_PATH=... GATE_MODEL_PATH=... \
    backend/.venv/Scripts/python.exe ml/scripts/build_demo_set.py --out "<folder>" [--prefer-correct]
"""

import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
DATA = ROOT / "ml" / "data"
EXTS = {".jpg", ".jpeg", ".png"}
GRADE = {"mild_dysplasia": "mild", "moderate_dysplasia": "moderate", "severe_dysplasia": "severe"}
PER_CLASS = 25


def candidates():
    """(path, truth grade, patient/case id, origin, used to train the grading model)."""
    held = {r["filename"] for r in csv.DictReader(open(DATA / "case_split_fixed" / "holdout" / "manifest.csv", encoding="utf-8"))}
    out = []
    for r in csv.DictReader(open(DATA / "client_cases" / "manifest.csv", encoding="utf-8")):
        if r["dx_group"] in GRADE:
            # The deployed grading model (v2 final) was trained on every graded client photo.
            out.append((DATA / "client_cases" / r["filename"], GRADE[r["dx_group"]], r["case_id"],
                        "client, biopsy-graded" + (" (held out from the cancer model)" if r["filename"] in held else ""), True))
    for folder, origin, trained in [
        (DATA / "kaggle_split_fixed" / "test" / "Non-Cancer", "Kaggle healthy, test split", False),
        (DATA / "fresh_test" / "Non-Cancer", "Kaggle healthy, untouched set", False),
        (DATA / "case_split_fixed" / "val" / "Non-Cancer", "Kaggle healthy, validation split", True),
    ]:
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in EXTS and not p.name.startswith(("relabelled_", "client_case")):
                out.append((p, "none", p.stem, origin, trained))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefer-correct", action="store_true",
                    help="choose photos the app answers correctly (demonstration only)")
    ap.add_argument("--reuse", action="store_true",
                    help="reuse the app results saved in artifacts/demo_candidates.csv instead of re-running the models")
    args = ap.parse_args()
    art = ROOT / "ml" / "artifacts" / "demo_candidates.csv"
    todo = candidates()
    rows = []
    if args.reuse:
        paths = {(p.name, origin): p for p, _, _, origin, _ in todo}
        for r in csv.DictReader(open(art, encoding="utf-8")):
            for k in ("in_grading_training", "accepted", "grade_correct", "cancer_correct"):
                r[k] = r[k] == "True"
            r["path"] = str(paths[(r["source_file"], r["origin"])])
            rows.append(r)
        todo = []
    else:
        from app.services.inference_service import inference_service as svc

        assert svc.enabled and svc.gate is not None, "set MODEL_PATH, GRADING_MODEL_PATH and GATE_MODEL_PATH"
    tmp = Path(tempfile.mkdtemp())
    for i, (path, truth, case, origin, trained) in enumerate(todo):
        row = {"source_file": path.name, "truth_grade": truth, "case": case, "origin": origin,
               "in_grading_training": trained, "accepted": False, "app_grade": "", "app_cancer": "", "path": str(path)}
        if svc.looks_like_oral_photo(path) and svc.quality_problem(path) is None:
            r = svc.predict(path, tmp / "h.png")
            row.update(accepted=True, app_grade=r.dysplasia_grade, app_cancer=r.assessment)
        row["grade_correct"] = row["app_grade"] == truth
        row["cancer_correct"] = row["app_cancer"] == "no_cancer"  # no candidate is a cancer
        rows.append(row)
        if i % 50 == 0:
            print(i, flush=True)
    shutil.rmtree(tmp, ignore_errors=True)

    if not args.reuse:
        with open(art, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != "path"], extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    print("\nAll candidates (app results):")
    for g in ["none", "mild", "moderate", "severe"]:
        rs = [r for r in rows if r["truth_grade"] == g]
        acc = [r for r in rs if r["accepted"]]
        print(f"  {g:9s} n={len(rs):3d} accepted={len(acc):3d} grade correct={sum(r['grade_correct'] for r in acc):3d} "
              f"cancer result 'no cancer'={sum(r['cancer_correct'] for r in acc):3d} both={sum(r['grade_correct'] and r['cancer_correct'] for r in acc):3d}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    key = []
    for g in ["none", "mild", "moderate", "severe"]:
        pool = [r for r in rows if r["truth_grade"] == g and r["accepted"]]
        right = [r for r in pool if r["grade_correct"] and r["cancer_correct"]]
        if args.prefer_correct and len(right) >= PER_CLASS:
            pool = right
        # Photos never used to train the grading model first; then (optionally) correct ones.
        pool.sort(key=lambda r: (not (r["grade_correct"] and r["cancer_correct"]) if args.prefer_correct else False,
                                 r["in_grading_training"], r["source_file"]))
        chosen, seen = [], set()
        for r in pool:  # one photo per patient first, so the set covers as many patients as possible
            if r["case"] not in seen and len(chosen) < PER_CLASS:
                chosen.append(r); seen.add(r["case"])
        for r in pool:
            if r not in chosen and len(chosen) < PER_CLASS:
                chosen.append(r)
        folder = out / {"none": "1_no_dysplasia", "mild": "2_mild_dysplasia", "moderate": "3_moderate_dysplasia", "severe": "4_severe_dysplasia"}[g]
        folder.mkdir(exist_ok=True)
        for n, r in enumerate(chosen, 1):
            name = f"{g}_{n:02d}{Path(r['path']).suffix.lower()}"
            shutil.copyfile(r["path"], folder / name)
            key.append({"file": f"{folder.name}/{name}", "true_grade": g, "true_cancer": "no cancer",
                        "truth_source": "histopathology (client case sheet)" if g != "none" else "public dataset label (healthy mouth)",
                        "app_grade": r["app_grade"], "app_cancer_result": r["app_cancer"].replace("_", " "),
                        "app_grade_correct": "yes" if r["grade_correct"] else "no",
                        "app_cancer_correct": "yes" if r["cancer_correct"] else "no",
                        "photo_was_in_grading_training": "yes" if r["in_grading_training"] else "no"})
    with open(out / "answer_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0]))
        w.writeheader()
        w.writerows(key)
    grade_ok = sum(k["app_grade_correct"] == "yes" for k in key)
    cancer_ok = sum(k["app_cancer_correct"] == "yes" for k in key)
    trained = sum(k["photo_was_in_grading_training"] == "yes" for k in key)
    (out / "README.txt").write_text(f"""OralSentinel demonstration set: {len(key)} photos, {PER_CLASS} per class
==================================================================

Folders: 1_no_dysplasia, 2_mild_dysplasia, 3_moderate_dysplasia, 4_severe_dysplasia.
answer_key.csv lists, for every photo, the true answer and what the app returned.
None of these photos is a cancer, so the correct cancer result is always "no cancer".

Where the true answers come from
- Mild, moderate and severe: the histopathology (biopsy) diagnosis on the clinic's case sheet.
- No dysplasia: healthy-mouth photos from the public Kaggle oral cancer dataset.

What the app returned on this set
- Dysplasia grade correct: {grade_ok} of {len(key)}
- Cancer result correct ("no cancer"): {cancer_ok} of {len(key)}

READ THIS BEFORE QUOTING THOSE NUMBERS
{"The photos were chosen because the app answers them correctly. " if args.prefer_correct else ""}{trained} of the {len(key)} photos were used to train the grading model, including every
dysplasia photo, so the app has seen them before. This set shows the app
working; it does not measure accuracy. On patients the app has never seen,
the dysplasia grade matched the biopsy for about 41 to 45% of patients, and
3 of 29 cancers in an untouched test set were called "no cancer".

These are real patient photos. Keep this folder on this computer; do not
upload it to a public site or share it without the clinic's permission.
""", encoding="utf-8")
    n = len(key)
    print(f"\nChosen set: {n} photos; grade correct {sum(k['app_grade_correct'] == 'yes' for k in key)}, "
          f"cancer result correct {sum(k['app_cancer_correct'] == 'yes' for k in key)}, "
          f"in grading training {sum(k['photo_was_in_grading_training'] == 'yes' for k in key)}")


if __name__ == "__main__":
    main()
