"""
Build a case-level (patient-level) client dataset from BOTH client sources.

The client supplied clinical photos two ways:
  1. Embedded in the treatment spreadsheet, one per row, next to that row's
     histopathology diagnosis.
  2. Two loose folders, "N c p.jpeg" (clinical) and "N H.jpeg" (histopath).

The folder numbering follows the spreadsheet's row order: folder case N is
spreadsheet row N+1. This was verified directly, not assumed -- the folder
histopath slides are pixel-identical to the spreadsheet's embedded histopath
images for 99 of 100 cases (rotation/mirror-invariant correlation 1.000),
every one consistent with N == row - 1. The folder CLINICAL photos are
different photographs of the same lesions (they never match the embedded
clinical photos exactly, but rank well above chance by colour similarity),
so each case contributes up to two distinct clinical photos.

Case 12 is the one histopath slide that does NOT match its expected row, so
its folder clinical photo is excluded as unverified.

Because most cases now have two photos, any train/val/test split MUST be by
case, never by image -- otherwise two shots of the same lesion land on both
sides of the split and the held-out number is inflated.

PHI: only image bytes, a binary label, a coarse diagnosis group, a case
index, and the source are written. No name, patient ID, or clinical note.

Usage:
    .venv/Scripts/python.exe scripts/prepare_client_cases.py <xlsx> <clinical_dir> <histopath_dir>

Output:
    ml/data/client_cases/<case>_<source>.jpg
    ml/data/client_cases/manifest.csv  (filename, case_id, source, label, dx_group)
"""

import csv
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_client_validation import DIAGNOSIS_COL_LETTER, map_label  # noqa: E402

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
EMBED_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
CLINICAL_COL, HISTOPATH_COL = 5, 6
HISTOPATH_MATCH_THRESHOLD = 0.95

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "client_cases"


def dx_group(diagnosis: str) -> str:
    """Coarse, non-identifying diagnosis group, most severe finding wins."""
    d = (diagnosis or "").lower()
    if re.search(r"\bscc\b|carcinoma", d):
        return "carcinoma"
    if "severe dysplasia" in d:
        return "severe_dysplasia"
    if "moderate dysplasia" in d:
        return "moderate_dysplasia"
    if "mild dysplasia" in d:
        return "mild_dysplasia"
    return "other"


def embedded_images(xlsx: Path) -> dict[int, dict[int, bytes]]:
    with zipfile.ZipFile(xlsx) as z:
        rels = z.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8")
        drawing = z.read("xl/drawings/drawing1.xml").decode("utf-8")
        media = {n.rsplit("/", 1)[-1]: z.read(n) for n in z.namelist() if n.startswith("xl/media/")}
    rid = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="\.\./media/([^"]+)"', rels))

    out: dict[int, dict[int, bytes]] = {CLINICAL_COL: {}, HISTOPATH_COL: {}}
    root = ET.fromstring(drawing)
    for anchor in root.findall("xdr:oneCellAnchor", NS) + root.findall("xdr:twoCellAnchor", NS):
        frm = anchor.find("xdr:from", NS)
        row = int(frm.find("xdr:row", NS).text) + 1
        col = int(frm.find("xdr:col", NS).text)
        blip = anchor.find(".//a:blip", NS)
        if col in out and blip is not None and rid.get(blip.get(EMBED_ATTR)) in media:
            out[col][row] = media[rid[blip.get(EMBED_ATTR)]]
    return out


def _desc(im: Image.Image) -> np.ndarray:
    a = np.asarray(im.convert("L").resize((16, 16), Image.BILINEAR), dtype=np.float32).ravel()
    return (a - a.mean()) / (a.std() + 1e-6)


def histopath_matches(embedded: bytes, folder_path: Path) -> bool:
    target = _desc(Image.open(folder_path).convert("RGB"))
    base = Image.open(io.BytesIO(embedded)).convert("RGB")
    for flip in (False, True):
        im = ImageOps.mirror(base) if flip else base
        for rot in (0, 90, 180, 270):
            v = _desc(im.rotate(rot, expand=True))
            if float(np.dot(v, target) / len(v)) >= HISTOPATH_MATCH_THRESHOLD:
                return True
    return False


def read_diagnoses(xlsx: Path, rows: set[int]) -> dict[int, str]:
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
    ws = wb.active
    out = {r: str(ws[f"{DIAGNOSIS_COL_LETTER}{r}"].value or "") for r in rows}
    wb.close()
    return out


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    xlsx, clin_dir, hist_dir = (Path(a) for a in sys.argv[1:])

    emb = embedded_images(xlsx)
    cases = range(1, 101)
    diagnoses = read_diagnoses(xlsx, {c + 1 for c in cases})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*"):
        old.unlink()

    rows_out, skipped = [], []
    for case in cases:
        row = case + 1
        label, group = map_label(diagnoses[row]), dx_group(diagnoses[row])

        if row in emb[CLINICAL_COL]:
            name = f"case{case:03d}_sheet.jpg"
            (OUT_DIR / name).write_bytes(emb[CLINICAL_COL][row])
            rows_out.append([name, case, "sheet", label, group])

        folder_clin = clin_dir / f"{case} c p.jpeg"
        folder_hist = hist_dir / f"{case} H.jpeg"
        verified = (
            row in emb[HISTOPATH_COL]
            and folder_hist.is_file()
            and histopath_matches(emb[HISTOPATH_COL][row], folder_hist)
        )
        if folder_clin.is_file() and verified:
            name = f"case{case:03d}_folder.jpg"
            (OUT_DIR / name).write_bytes(folder_clin.read_bytes())
            rows_out.append([name, case, "folder", label, group])
        elif folder_clin.is_file():
            skipped.append(case)

    with (OUT_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "case_id", "source", "label", "dx_group"])
        w.writerows(rows_out)

    n_cases = len({r[1] for r in rows_out})
    print(f"Wrote {len(rows_out)} photos from {n_cases} cases to {OUT_DIR}")
    print(f"  from spreadsheet: {sum(r[2] == 'sheet' for r in rows_out)}")
    print(f"  from folder (histopath-verified): {sum(r[2] == 'folder' for r in rows_out)}")
    print(f"  folder photos excluded, histopath did not verify: {skipped}")
    labels = {}
    for r in rows_out:
        labels.setdefault(r[3], set()).add(r[1])
    print("  cases per label:", {k: len(v) for k, v in labels.items()})


if __name__ == "__main__":
    main()
