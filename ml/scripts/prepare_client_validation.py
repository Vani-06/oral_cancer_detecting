"""
Extract a PHI-free external validation set from the client's treatment spreadsheet.

The spreadsheet (not checked into this repo, never will be) embeds a clinical
and a histopath photo directly in each patient's row, next to a free-text
histopathology diagnosis. This script pulls out ONLY the clinical photo and a
binary label derived from that diagnosis text -- no name, no patient ID, no
clinical notes ever reach the output.

Verified this only works via the row's cell anchor in the drawing XML, not by
filename or row order: earlier testing showed the separately-provided
numbered image folders do NOT correspond to this spreadsheet at all (checked
by exact hash and by perceptual-hash nearest-neighbor search across every
possible pairing). Those folders are intentionally not touched here.

Usage:
    .venv/Scripts/python.exe scripts/prepare_client_validation.py <path-to-xlsx>

Output:
    ml/data/client_validation/val_001.jpg, val_002.jpg, ...
    ml/data/client_validation/manifest.csv   (filename, label -- nothing else)
"""

import csv
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

CANCER_PATTERN = re.compile(r"\bSCC\b|carcinoma", re.IGNORECASE)

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

CLINICAL_IMAGE_COL = 5  # 0-indexed column F ("clinical image"), from the sheet header
DIAGNOSIS_COL_LETTER = "E"  # "FieldValue" -- the histopathology diagnosis text


def map_label(diagnosis: str) -> str:
    """Collapse the real diagnosis spectrum to the app's binary label.

    Only a diagnosis explicitly naming SCC/carcinoma is treated as Cancer.
    Everything else -- dysplasia grades, OSMF, PVL, hyperkeratosis alone -- is
    Non-Cancer. This is a simplification, documented in model_card.md: the
    client set has exactly one confirmed-cancer case, nowhere near enough to
    support a finer-grained taxonomy.
    """
    return "Cancer" if CANCER_PATTERN.search(diagnosis or "") else "Non-Cancer"


def extract_row_to_media(xlsx_path: Path) -> dict[int, str]:
    """Map sheet row -> embedded clinical-image media filename (e.g. image1.jpg).

    Uses the drawing XML's cell anchors, which is a structural fact about
    which row an image is embedded in -- not an assumption or a guess.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        rels_xml = z.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8")
        drawing_xml = z.read("xl/drawings/drawing1.xml").decode("utf-8")

    rid_to_file = dict(
        re.findall(r'Id="(rId\d+)"[^>]*Target="\.\./media/([^"]+)"', rels_xml)
    )

    root = ET.fromstring(drawing_xml)
    row_to_media: dict[int, str] = {}
    for anchor in root.findall("xdr:oneCellAnchor", NS) + root.findall(
        "xdr:twoCellAnchor", NS
    ):
        frm = anchor.find("xdr:from", NS)
        row = int(frm.find("xdr:row", NS).text) + 1  # 0-indexed -> 1-indexed sheet row
        col = int(frm.find("xdr:col", NS).text)
        if col != CLINICAL_IMAGE_COL:
            continue
        blip = anchor.find(".//a:blip", NS)
        if blip is None:
            continue
        rid = blip.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        )
        fname = rid_to_file.get(rid)
        if fname:
            row_to_media[row] = fname

    return row_to_media


def extract_row_diagnoses(xlsx_path: Path, rows_needed: set[int]) -> dict[int, str]:
    """Read only the FieldValue (diagnosis) cell for the rows we have images for.

    Deliberately does not use openpyxl's full-row iteration here to avoid ever
    holding the PatientName/PID/clinical-notes columns in memory for longer
    than necessary -- import is scoped to this function only.
    """
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb.active

    diagnoses: dict[int, str] = {}
    for row_idx in rows_needed:
        cell = ws[f"{DIAGNOSIS_COL_LETTER}{row_idx}"]
        diagnoses[row_idx] = str(cell.value or "")
    wb.close()
    return diagnoses


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: prepare_client_validation.py <path-to-treatment-xlsx>")
        sys.exit(1)

    xlsx_path = Path(sys.argv[1])
    if not xlsx_path.is_file():
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    out_dir = Path(__file__).resolve().parent.parent / "data" / "client_validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    row_to_media = extract_row_to_media(xlsx_path)
    print(f"Found {len(row_to_media)} rows with an embedded clinical image.")

    diagnoses = extract_row_diagnoses(xlsx_path, set(row_to_media.keys()))

    with zipfile.ZipFile(xlsx_path) as z:
        media_bytes = {
            name.rsplit("/", 1)[-1]: z.read(name)
            for name in z.namelist()
            if name.startswith("xl/media/")
        }

    manifest_rows = []
    label_counts = {"Cancer": 0, "Non-Cancer": 0}

    for i, row in enumerate(sorted(row_to_media.keys()), start=1):
        media_name = row_to_media[row]
        data = media_bytes.get(media_name)
        if data is None:
            print(f"  skipping row {row}: media {media_name} not found in archive")
            continue

        label = map_label(diagnoses.get(row, ""))
        label_counts[label] += 1

        out_name = f"val_{i:03d}.jpg"
        (out_dir / out_name).write_bytes(data)
        manifest_rows.append({"filename": out_name, "label": label})

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "label"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nWrote {len(manifest_rows)} images + manifest to {out_dir}")
    print(f"Label distribution: {label_counts}")
    print(
        "\nReminder: this set is for external validation only. With "
        f"{label_counts['Cancer']} confirmed-cancer case(s), it cannot "
        "measure cancer-detection sensitivity -- only whether the model "
        "avoids false Cancer calls on precancerous lesions."
    )


if __name__ == "__main__":
    main()
