"""Basic photo-quality check (review item 23)."""

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from app.services.photo_quality import quality_problem


def textured(seed=0):
    rng = np.random.default_rng(seed)
    base = rng.integers(60, 200, (360, 480, 3), dtype=np.uint8)
    return Image.fromarray(base).filter(ImageFilter.GaussianBlur(1))


def test_a_detailed_well_lit_photo_passes():
    assert quality_problem(textured()) is None


def test_dark_washed_out_and_blurred_photos_are_refused_with_a_reason():
    photo = textured()
    assert "too dark" in quality_problem(ImageEnhance.Brightness(photo).enhance(0.1))
    assert "washed out" in quality_problem(ImageEnhance.Brightness(photo).enhance(4.0))
    assert "blurred" in quality_problem(photo.filter(ImageFilter.GaussianBlur(20)))
    assert "blurred" in quality_problem(photo.resize((24, 24)).resize(photo.size))
