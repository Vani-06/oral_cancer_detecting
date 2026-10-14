"""
Generates the downloadable PDF report for a completed prediction.

Replaces the earlier hand-built raw PDF bytes (which could not embed images)
with reportlab, so the report carries the actual uploaded photo and, once a
model is configured, its Grad-CAM heatmap alongside the dysplasia grade and
the cancer detection result -- not just text. No model score is printed.
"""

from pathlib import Path

from PIL import Image as PILImage, ImageOps, UnidentifiedImageError
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.models import Prediction

PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN = 0.75 * inch
IMAGE_MAX_WIDTH = (PAGE_WIDTH - 2 * MARGIN - 0.3 * inch) / 2
IMAGE_MAX_HEIGHT = 3.2 * inch

DISCLAIMER = (
    "This software is an investigational research aid, not a medical device. "
    "It does not provide a diagnosis. Clinical examination and histopathology "
    "remain required for any diagnostic decision."
)

# Same labels as METADATA_FIELD_LABELS in frontend/src/lib/metadataSchema.ts.
METADATA_LABELS = {
    "patient_reference": "Patient ID",
    "age": "Age",
    "sex": "Sex",
    "tobacco_use": "Tobacco use",
    "tobacco_type": "Tobacco type",
    "tobacco_years": "Years of tobacco use",
    "betel_quid_use": "Betel quid / areca nut",
    "betel_quid_years": "Years of betel quid use",
    "alcohol_use": "Alcohol use",
    "lesion_site": "Lesion site",
    "lesion_duration_weeks": "Lesion duration (weeks)",
    "pain": "Pain",
    "bleeding": "Bleeding",
    "prior_lesion_history": "Prior oral lesion",
    "medical_history": "Medical history",
    "clinical_notes": "Clinical notes",
}

# Values that are enum keys (buccal_mucosa -> Buccal mucosa). Free text such
# as clinical notes is printed exactly as entered.
ENUM_FIELDS = {"sex", "tobacco_type", "lesion_site"}
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN


def grade_text(grade: str | None) -> str:
    return f"{grade.capitalize()} dysplasia" if grade else "Not available"


def cancer_text(label: str | None) -> str:
    return {"Cancer": "Cancer detected", "Non-Cancer": "No cancer detected"}.get(label or "", "Pending")


def _format_metadata_value(key: str, value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key in ENUM_FIELDS and isinstance(value, str):
        return value.replace("_", " ").capitalize()
    return str(value)


def _draw_image_fit(c: canvas.Canvas, path: Path, x: float, y: float) -> bool:
    """Draws an image scaled to fit within IMAGE_MAX_WIDTH x IMAGE_MAX_HEIGHT,
    anchored at top-left (x, y is the TOP of the image box). Returns whether
    the image was actually drawn -- a report must still generate if a stored
    file turns out to be missing or corrupt (partial write, disk issue), not
    500 on what should be a routine PDF download."""
    try:
        with PILImage.open(path) as raw:
            # Upright, as the browser shows it -- reportlab ignores EXIF
            # orientation, so phone photos would otherwise print sideways.
            im = ImageOps.exif_transpose(raw).convert("RGB")
    except (OSError, UnidentifiedImageError):
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(x, y - 0.2 * inch, "[image unavailable]")
        return False

    w, h = im.size
    scale = min(IMAGE_MAX_WIDTH / w, IMAGE_MAX_HEIGHT / h)
    draw_w, draw_h = w * scale, h * scale
    c.drawImage(ImageReader(im), x, y - draw_h, width=draw_w, height=draw_h, preserveAspectRatio=True)
    return True


def generate_report_pdf(prediction: Prediction, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=LETTER)

    y = PAGE_HEIGHT - MARGIN

    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, "Oral Lesion Analysis Report")
    y -= 0.35 * inch

    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, y, f"Case ID: {prediction.prediction_id}")
    y -= 0.2 * inch
    c.drawString(MARGIN, y, f"Date: {prediction.created_at.isoformat()}")
    y -= 0.4 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, y, f"1. Dysplasia grade: {grade_text(prediction.dysplasia_grade)}")
    y -= 0.24 * inch
    c.drawString(MARGIN, y, f"2. Cancer detection: {cancer_text(prediction.prediction)}")
    y -= 0.45 * inch

    image_top = y
    image_path = Path(settings.UPLOAD_DIR) / prediction.filename
    if image_path.is_file():
        _draw_image_fit(c, image_path, MARGIN, image_top)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(MARGIN, image_top - IMAGE_MAX_HEIGHT - 0.15 * inch, "Uploaded image")

    if prediction.heatmap_path:
        heatmap_path = Path(settings.UPLOAD_DIR) / "heatmaps" / prediction.heatmap_path
        if heatmap_path.is_file():
            heatmap_x = MARGIN + IMAGE_MAX_WIDTH + 0.3 * inch
            _draw_image_fit(c, heatmap_path, heatmap_x, image_top)
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(
                heatmap_x, image_top - IMAGE_MAX_HEIGHT - 0.15 * inch,
                "Grad-CAM explainability heatmap",
            )

    y = image_top - IMAGE_MAX_HEIGHT - 0.5 * inch

    if prediction.metadata_json:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, "Patient context")
        y -= 0.2 * inch
        # Known fields in form order, then anything unrecognised (older rows).
        keys = [k for k in METADATA_LABELS if k in prediction.metadata_json]
        keys += [k for k in prediction.metadata_json if k not in METADATA_LABELS]
        for key in keys:
            label = METADATA_LABELS.get(key, key)
            text = f"{label}: {_format_metadata_value(key, prediction.metadata_json[key])}"
            # Wrapped, and continued on a new page -- clinical notes can be
            # long, and silently cutting fields off a medical report is worse
            # than a second page.
            for line in simpleSplit(text, "Helvetica", 9, TEXT_WIDTH):
                if y < MARGIN + 0.8 * inch:
                    c.showPage()
                    y = PAGE_HEIGHT - MARGIN
                c.setFont("Helvetica", 9)
                c.drawString(MARGIN, y, line)
                y -= 0.16 * inch
        y -= 0.2 * inch

    c.setFont("Helvetica-Oblique", 8)
    text_obj = c.beginText(MARGIN, max(y, MARGIN + 0.3 * inch))
    text_obj.setLeading(11)
    # Simple manual wrap -- the disclaimer is a fixed, known string, so this
    # doesn't need a general-purpose text-wrapping library.
    words = DISCLAIMER.split()
    line = ""
    max_chars = 95
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > max_chars:
            text_obj.textLine(line)
            line = word
        else:
            line = candidate
    if line:
        text_obj.textLine(line)
    c.drawText(text_obj)

    c.showPage()
    c.save()
