"""Exercises the real inference -> Grad-CAM -> report path.

Uses a randomly initialised ResNet-50 checkpoint in the checkpoint format
ml/scripts/train.py writes, so the tests don't depend on the (gitignored)
trained weights. Predictions are meaningless; the plumbing is what's tested.
"""

import json
from pathlib import Path

import pytest
import torch
from PIL import Image
from torchvision.models import resnet50

from conftest import VALID_METADATA, jpeg_bytes
from app.core.config import settings
from app.services import inference_service as inference_module
from app.services import prediction_service as prediction_module


@pytest.fixture(scope="module")
def enabled_inference(tmp_root):
    model = resnet50(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    ckpt = tmp_root / "random_model.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "class_to_idx": {"Cancer": 0, "Non-Cancer": 1},
            "img_size": 224,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        ckpt,
    )
    original_path, original_service = settings.MODEL_PATH, prediction_module.inference_service
    settings.MODEL_PATH = str(ckpt)
    service = inference_module.InferenceService()
    assert service.enabled
    prediction_module.inference_service = service
    yield service
    prediction_module.inference_service = original_service
    settings.MODEL_PATH = original_path


def post(client, auth, content=None, metadata=None):
    data = {"metadata_json": json.dumps(metadata)} if metadata else {}
    files = {"file": ("lesion.jpg", content or jpeg_bytes(), "image/jpeg")}
    resp = client.post("/predict", headers=auth, files=files, data=data)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_inference_populates_result_and_report_link(client, auth, enabled_inference):
    body = post(client, auth, metadata=VALID_METADATA)
    assert body["prediction"] in {"Cancer", "Non-Cancer"}
    assert 0.5 <= body["confidence"] <= 1.0
    assert body["is_pending_inference"] is False
    assert body["heatmap_url"].startswith("/uploads/heatmaps/")
    assert body["pdf_url"] == f"/reports/{body['prediction_id']}"

    heatmap_name = body["heatmap_url"].rsplit("/", 1)[-1]
    assert heatmap_name != f"{body['prediction_id']}.png", "heatmap name must not be guessable"
    assert client.get(body["heatmap_url"]).status_code == 200

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
    assert 0.0 <= body["confidence"] <= 1.0


def test_exif_rotated_photo_heatmap_matches_upright_orientation(client, auth, enabled_inference):
    # Stored 320x240 with EXIF orientation 6 (rotate 90): displayed as 240x320.
    body = post(client, auth, content=jpeg_bytes(size=(320, 240), exif_orientation=6))
    heatmap = Path(settings.UPLOAD_DIR) / "heatmaps" / body["heatmap_url"].rsplit("/", 1)[-1]
    with Image.open(heatmap) as im:
        assert im.size == (240, 320)
