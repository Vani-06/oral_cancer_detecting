"""
Basic photo-quality check, run before the analysis.

The photo check (PhotoGate) asks "is this an oral photo?" by content, so it
accepts oral photos that are far too dark, washed out or low in detail to
analyse (review item 23: it accepted 99% of very dark and 67% of tiny
upscaled test photos). These three measures catch those. Each cut-off sits
below every one of 749 training, 135 test and 100 real clinical oral photos
(ml/scripts/photo_quality_stats.py), so no usable photo in those sets is
refused.
"""

import numpy as np
from PIL import Image, ImageFilter

# Mean brightness (0-1) below which the photo is too dark.
MIN_BRIGHTNESS = 0.15
# Share of almost-white pixels above which the photo is washed out.
MAX_OVEREXPOSED = 0.50
# Fine detail (mean edge strength on a 512 px greyscale copy) below
# which the photo is too blurred or too low in resolution.
MIN_DETAIL = 1.35


def measure(image: Image.Image) -> dict[str, float]:
    grey = image.convert("L")
    grey.thumbnail((512, 512))
    pixels = np.asarray(grey, dtype=np.float32) / 255.0
    edges = np.asarray(grey.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    # FIND_EDGES leaves a border artefact; ignore the outer pixels.
    detail = float(edges[2:-2, 2:-2].mean()) if min(edges.shape) > 4 else 0.0
    return {
        "brightness": float(pixels.mean()),
        "overexposed": float((pixels > 0.96).mean()),
        "detail": detail,
    }


def quality_problem(image: Image.Image) -> str | None:
    """A message for the clinician when the photo cannot be analysed, else None."""
    m = measure(image)
    if m["brightness"] < MIN_BRIGHTNESS:
        return "The photo is too dark to analyse. Retake it with more light."
    if m["overexposed"] > MAX_OVEREXPOSED:
        return "Too much of the photo is washed out by light or flash glare. Retake it without direct glare."
    if m["detail"] < MIN_DETAIL:
        return "The photo is too blurred or too low in resolution to analyse. Retake it in focus, closer to the lesion."
    return None
