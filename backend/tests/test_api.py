import json
import re
import re

from conftest import VALID_METADATA, jpeg_bytes, register


def upload(client, headers, data=None, filename="lesion.jpg", content=None):
    files = {"file": (filename, content or jpeg_bytes(), "image/jpeg")}
    return client.post("/predict", headers=headers, files=files, data=data or {})


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_register_login_me(client):
    email = "flow@clinic.org"
    reg = client.post(
        "/register", json={"email": email, "password": "password123", "full_name": "Flow"}
    )
    assert reg.status_code == 201
    login = client.post("/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == email


def test_wrong_password_rejected(client):
    client.post("/register", json={"email": "pw@clinic.org", "password": "password123", "full_name": "P"})
    assert client.post("/login", json={"email": "pw@clinic.org", "password": "nope-nope"}).status_code == 401


def test_upload_requires_auth(client):
    assert upload(client, headers={}).status_code == 401


def test_upload_rejects_non_image_extension(client, auth):
    resp = upload(client, auth, filename="notes.txt", content=b"hello")
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_without_model_stays_pending(client, auth):
    resp = upload(client, auth)
    assert resp.status_code == 201
    body = resp.json()
    assert body["prediction"] == "Pending"
    assert body["is_pending_inference"] is True
    assert body["pdf_url"] is None

    detail = client.get(f"/predictions/{body['prediction_id']}", headers=auth).json()
    assert detail["pdf_url"] is None
    assert client.get(f"/reports/{body['prediction_id']}", headers=auth).status_code == 400


def test_valid_metadata_is_stored(client, auth):
    resp = upload(client, auth, data={"metadata_json": json.dumps(VALID_METADATA)})
    assert resp.status_code == 201
    detail = client.get(f"/predictions/{resp.json()['prediction_id']}", headers=auth).json()
    assert detail["metadata"] == VALID_METADATA


def test_metadata_is_validated_at_the_api_boundary(client, auth):
    bad_cases = [
        "not json",
        json.dumps([1, 2, 3]),
        json.dumps({**VALID_METADATA, "age": 500}),
        json.dumps({**VALID_METADATA, "lesion_site": "elbow"}),
        json.dumps({**VALID_METADATA, "unexpected_field": "x"}),
        json.dumps({**VALID_METADATA, "tobacco_type": None, "tobacco_years": None}),
    ]
    for raw in bad_cases:
        resp = upload(client, auth, data={"metadata_json": raw})
        assert resp.status_code == 400, f"accepted invalid metadata: {raw}"


def test_users_cannot_see_each_others_predictions(client):
    alice, bob = register(client), register(client)
    pid = upload(client, alice).json()["prediction_id"]
    assert client.get(f"/predictions/{pid}", headers=bob).status_code == 404
    assert client.get(f"/reports/{pid}", headers=bob).status_code == 404
    assert all(p["prediction_id"] != pid for p in client.get("/predictions", headers=bob).json())


# Fields from the client's own case sheet (07-05-2025_Treatment.xlsx): patient
# ID, habit duration, medical history and clinical notes, plus sites it uses.
CASE_SHEET_METADATA = {
    **VALID_METADATA,
    "patient_reference": "OPD-2025-0412",
    "tobacco_use": False,
    "tobacco_type": None,
    "tobacco_years": None,
    "betel_quid_years": 10,
    "lesion_site": "retromolar_trigone",
    "medical_history": "Diabetes, hypertension 5 years",
    "clinical_notes": "Non scrapable white patch irt left buccal mucosa",
}


def test_case_sheet_fields_are_accepted_and_stored(client, auth):
    resp = upload(client, auth, data={"metadata_json": json.dumps(CASE_SHEET_METADATA)})
    assert resp.status_code == 201, resp.text
    detail = client.get(f"/predictions/{resp.json()['prediction_id']}", headers=auth).json()
    assert detail["metadata"] == {k: v for k, v in CASE_SHEET_METADATA.items() if v is not None}


def test_case_sheet_optional_fields_can_be_omitted(client, auth):
    minimal = {k: v for k, v in VALID_METADATA.items() if k != "lesion_duration_weeks"}
    blank_text = {**minimal, "medical_history": "   ", "clinical_notes": ""}
    for meta in (minimal, blank_text):
        resp = upload(client, auth, data={"metadata_json": json.dumps(meta)})
        assert resp.status_code == 201, resp.text
        stored = client.get(f"/predictions/{resp.json()['prediction_id']}", headers=auth).json()["metadata"]
        assert "medical_history" not in stored and "clinical_notes" not in stored


def test_case_sheet_field_limits(client, auth):
    for bad in (
        {"clinical_notes": "x" * 2001},
        {"medical_history": "x" * 1001},
        {"patient_reference": "x" * 65},
        {"betel_quid_years": -1},
    ):
        resp = upload(client, auth, data={"metadata_json": json.dumps({**VALID_METADATA, **bad})})
        assert resp.status_code == 400, f"accepted {bad}"


def test_report_keeps_long_notes_on_extra_pages(tmp_root):
    from datetime import datetime
    from types import SimpleNamespace

    from app.services.report_service import generate_report_pdf

    record = SimpleNamespace(
        prediction_id=1,
        created_at=datetime(2026, 1, 1),
        prediction="Non-Cancer",
        confidence=0.8,
        dysplasia_grade="moderate",
        filename="missing.jpg",
        heatmap_path=None,
        metadata_json={**CASE_SHEET_METADATA, "clinical_notes": "word " * 399},
    )
    out = tmp_root / "long-notes.pdf"
    generate_report_pdf(record, out)
    page_count = int(re.search(rb"/Count (\d+)", out.read_bytes()).group(1))
    # ~2000 characters of notes cannot fit under the images on page one; the
    # old renderer silently dropped them instead of continuing.
    assert page_count == 2


def test_patient_images_require_the_owners_token(client):
    alice, bob = register(client), register(client)
    body = upload(client, alice).json()
    image_url = body["image_url"]
    assert image_url == f"/predictions/{body['prediction_id']}/image"

    owner = client.get(image_url, headers=alice)
    assert owner.status_code == 200
    assert owner.headers["cache-control"] == "private, no-store"
    assert client.get(image_url).status_code == 401
    assert client.get(image_url, headers=bob).status_code == 404


def test_upload_directory_is_not_publicly_served(client, auth, tmp_root):
    upload(client, auth)
    stored = next((tmp_root / "uploads").glob("*.jpg"))
    assert client.get(f"/uploads/{stored.name}").status_code == 404
