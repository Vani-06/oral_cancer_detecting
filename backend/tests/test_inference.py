"""Exercises the real inference -> Grad-CAM -> report path.

Uses a randomly initialised ResNet-50 checkpoint in the checkpoint format
ml/scripts/train.py writes, so the tests don't depend on the (gitignored)
trained weights. Predictions are meaningless; the plumbing is what's tested.
"""

import io
import json
from pathlib import Path

import pytest
import torch
from PIL import Image
from torchvision.models import resnet50

from conftest import VALID_METADATA, jpeg_bytes, register
from app.core.config import settings
from app.services import inference_service as inference_module
from app.services import prediction_service as prediction_module


GRADES = {"mild_dysplasia": 0, "moderate_dysplasia": 1, "severe_dysplasia": 2}


def save_random_checkpoint(path, class_to_idx):
    torch.manual_seed(0)
    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(class_to_idx))
    # Small head weights keep P(Cancer) strictly inside (0, 1). With default
    # init the untrained backbone's activations can saturate softmax to
    # exactly 1.0 in float32, which made the threshold test flaky.
    torch.nn.init.normal_(model.fc.weight, std=1e-4)
    torch.nn.init.zeros_(model.fc.bias)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "class_to_idx": class_to_idx,
            "img_size": 224,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        path,
    )
    return str(path)


@pytest.fixture(scope="module")
def enabled_inference(tmp_root):
    original = settings.MODEL_PATH, settings.GRADING_MODEL_PATH, prediction_module.inference_service
    settings.MODEL_PATH = save_random_checkpoint(tmp_root / "random_model.pt", {"Cancer": 0, "Non-Cancer": 1})
    settings.GRADING_MODEL_PATH = save_random_checkpoint(tmp_root / "random_grading.pt", GRADES)
    service = inference_module.InferenceService()
    assert service.enabled and service.grading_enabled
    prediction_module.inference_service = service
    yield service
    settings.MODEL_PATH, settings.GRADING_MODEL_PATH, prediction_module.inference_service = original


def post(client, auth, content=None, metadata=None):
    data = {"metadata_json": json.dumps(metadata)} if metadata else {}
    files = {"file": ("lesion.jpg", content or jpeg_bytes(), "image/jpeg")}
    resp = client.post("/predict", headers=auth, files=files, data=data)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_inference_populates_result_and_report_link(client, auth, enabled_inference):
    body = post(client, auth, metadata=VALID_METADATA)
    assert body["prediction"] in {"Cancer", "Non-Cancer"}
    assert body["is_pending_inference"] is False
    assert body["heatmap_url"] == f"/predictions/{body['prediction_id']}/heatmap"
    assert body["pdf_url"] == f"/reports/{body['prediction_id']}"

    resp = client.get(body["heatmap_url"], headers=auth)
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"
    assert client.get(body["heatmap_url"]).status_code == 401
    assert client.get(body["heatmap_url"], headers=register(client)).status_code == 404

    # The stored file name is still random (defence in depth), not {id}.png.
    assert not (Path(settings.UPLOAD_DIR) / "heatmaps" / f"{body['prediction_id']}.png").exists()

    detail = client.get(f"/predictions/{body['prediction_id']}", headers=auth).json()
    assert detail["pdf_url"] == body["pdf_url"]


def test_report_is_authenticated_and_not_publicly_served(client, auth, enabled_inference):
    pid = post(client, auth, metadata=VALID_METADATA)["prediction_id"]

    resp = client.get(f"/reports/{pid}", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    report_file = Path(settings.REPORT_DIR) / f"{pid}.pdf"
    assert report_file.is_file()
    assert Path(settings.UPLOAD_DIR) not in report_file.parents
    assert client.get(f"/uploads/reports/{pid}.pdf").status_code == 404
    assert client.get(f"/reports/{pid}").status_code == 401


def test_report_regenerates_when_file_is_missing(client, auth, enabled_inference):
    pid = post(client, auth)["prediction_id"]
    assert client.get(f"/reports/{pid}", headers=auth).status_code == 200
    (Path(settings.REPORT_DIR) / f"{pid}.pdf").unlink()
    resp = client.get(f"/reports/{pid}", headers=auth)
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")


def test_cancer_threshold_controls_the_label(client, auth, enabled_inference, monkeypatch):
    monkeypatch.setattr(settings, "CANCER_THRESHOLD", 1e-9)
    assert post(client, auth)["prediction"] == "Cancer"
    monkeypatch.setattr(settings, "CANCER_THRESHOLD", 1 - 1e-9)
    body = post(client, auth)
    assert body["prediction"] == "Non-Cancer"


def test_exif_rotated_photo_heatmap_matches_upright_orientation(client, auth, enabled_inference):
    # Stored 320x240 with EXIF orientation 6 (rotate 90): displayed as 240x320.
    body = post(client, auth, content=jpeg_bytes(size=(320, 240), exif_orientation=6))
    heatmap = client.get(body["heatmap_url"], headers=auth).content
    with Image.open(io.BytesIO(heatmap)) as im:
        assert im.size == (240, 320)


def test_result_has_grade_then_cancer_and_never_a_score(client, auth, enabled_inference):
    body = post(client, auth)
    assert body["dysplasia_grade"] in {"mild", "moderate", "severe"}
    assert body["prediction"] in {"Cancer", "Non-Cancer"}

    pid = body["prediction_id"]
    detail = client.get(f"/predictions/{pid}", headers=auth).json()
    history = client.get("/predictions", headers=auth).json()
    for payload in (body, detail, *history):
        assert "confidence" not in payload, "model scores must never be sent to clients"
    assert detail["dysplasia_grade"] == body["dysplasia_grade"]
    assert next(h for h in history if h["prediction_id"] == pid)["dysplasia_grade"] == body["dysplasia_grade"]


def test_grade_is_absent_without_a_grading_model(client, auth, enabled_inference, monkeypatch):
    monkeypatch.setattr(enabled_inference, "grading_enabled", False)
    body = post(client, auth)
    assert body["prediction"] in {"Cancer", "Non-Cancer"}
    assert body["dysplasia_grade"] is None


def test_report_shows_grade_and_detection_but_no_score(tmp_root):
    from datetime import datetime
    from types import SimpleNamespace

    from app.services import report_service

    lines = []
    original = report_service.canvas.Canvas.drawString
    report_service.canvas.Canvas.drawString = lambda self, x, y, text, *a, **k: (lines.append(text), original(self, x, y, text, *a, **k))[1]
    try:
        record = SimpleNamespace(
            prediction_id=7, created_at=datetime(2026, 1, 1), prediction="Non-Cancer", confidence=0.93,
            dysplasia_grade="severe", filename="missing.jpg", heatmap_path=None, metadata_json=None,
        )
        report_service.generate_report_pdf(record, tmp_root / "graded.pdf")
    finally:
        report_service.canvas.Canvas.drawString = original

    assert "1. Dysplasia grade: Severe dysplasia" in lines
    assert "2. Cancer detection: No cancer detected" in lines
    assert not any("%" in line or "onfidence" in line for line in lines)
