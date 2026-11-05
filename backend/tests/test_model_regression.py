"""Model regression test: the deployed models must keep giving the same
results on fixed held-out client photos. Skipped when the trained model
files or data are not present (they are not in version control)."""

import tempfile
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parents[2] / "ml"
MODELS = {
    "MODEL_PATH": ML / "artifacts" / "resnet50_oral_cancer_v7.pt",
    "GATE_MODEL_PATH": ML / "artifacts" / "oral_photo_gate_v1.pt",
    "GRADING_MODEL_PATH": ML / "artifacts" / "resnet50_dysplasia_grade_v2.pt",
}
PHOTOS = ML / "data" / "case_split" / "holdout"
# (photo, label, three-way result, grade, consensus score) recorded 6 Nov 2026.
EXPECTED = [
    ("case004_sheet.jpg", "Non-Cancer", "no_cancer", "moderate", 0.0053),
    ("case014_folder.jpg", "Non-Cancer", "inconclusive", "severe", 0.2454),
    ("case089_sheet.jpg", "Non-Cancer", "inconclusive", "moderate", 0.1801),
]


@pytest.mark.skipif(not all(p.is_file() for p in MODELS.values()) or not PHOTOS.is_dir(),
                    reason="trained models or held-out photos not present")
def test_fixed_photos_give_the_recorded_results(monkeypatch):
    from app.core.config import settings
    from app.services import inference_service as inference_module

    for name, path in MODELS.items():
        monkeypatch.setattr(settings, name, str(path))
    service = inference_module.InferenceService()
    out = Path(tempfile.mkdtemp())
    for name, label, assessment, grade, score in EXPECTED:
        result = service.predict(PHOTOS / name, out / "heatmap.png")
        assert (result.label, result.assessment, result.dysplasia_grade) == (label, assessment, grade), name
        assert service._consensus_score(inference_module._open_photo(PHOTOS / name)) == pytest.approx(score, abs=1e-3)
