"""Referral workflow, audit log, deletion, retention, consent, result
feedback (review items 39, 46, 49) and account security (item 45)."""

import time
import uuid

import pytest

from conftest import CONSENT, jpeg_bytes, register
from app.core import totp
from app.core.config import settings
from app.models import AuditEvent, User
from app.db import SessionLocal


def upload(client, auth, consent=True):
    files = {"file": ("lesion.jpg", jpeg_bytes(), "image/jpeg")}
    return client.post("/predict", headers=auth, files=files, data=CONSENT if consent else {})


def actions(user_email):
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == user_email).one()
        return [e.action for e in db.query(AuditEvent).filter(AuditEvent.user_id == user.id).all()]


# --- consent, follow-up, feedback, deletion, audit ---

def test_upload_requires_patient_consent(client, auth):
    resp = upload(client, auth, consent=False)
    assert resp.status_code == 400 and "consent" in resp.json()["detail"]
    ok = upload(client, auth)
    assert ok.status_code == 201
    detail = client.get(f"/predictions/{ok.json()['prediction_id']}", headers=auth).json()
    assert detail["consent_at"] is not None


def test_follow_up_can_be_recorded(client, auth):
    pid = upload(client, auth).json()["prediction_id"]
    resp = client.patch(f"/predictions/{pid}/follow-up", headers=auth,
                        json={"status": "referred", "note": "Referred to oral medicine, 12 Nov"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["follow_up"] == "referred" and body["follow_up_note"].startswith("Referred")
    assert client.patch(f"/predictions/{pid}/follow-up", headers=auth, json={"status": "lost"}).status_code == 422
    # Another clinician cannot touch it.
    assert client.patch(f"/predictions/{pid}/follow-up", headers=register(client),
                        json={"status": "closed"}).status_code == 404


def test_cancer_or_inconclusive_results_start_as_follow_up_needed(client, auth, monkeypatch):
    from app.routers import prediction as prediction_router
    from app.services.inference_service import InferenceResult

    class Fake:
        enabled = True

        def looks_like_oral_photo(self, path):
            return True

        def predict(self, image_path, heatmap_output_path, reference_path=None):
            return InferenceResult(label="Cancer", confidence=0.9, dysplasia_grade="severe",
                                   assessment="inconclusive", reference_status=None)

    from app.services import prediction_service
    monkeypatch.setattr(prediction_service, "inference_service", Fake())
    pid = upload(client, auth).json()["prediction_id"]
    detail = client.get(f"/predictions/{pid}", headers=auth).json()
    assert detail["follow_up"] == "needed"
    assert prediction_router  # imported for patch scope


def test_wrong_result_can_be_reported(client, auth):
    pid = upload(client, auth).json()["prediction_id"]
    resp = client.post(f"/predictions/{pid}/feedback", headers=auth,
                       json={"kind": "cancer_result_wrong", "actual_diagnosis": "Lichen planus on biopsy"})
    assert resp.status_code == 201
    assert client.get(f"/predictions/{pid}", headers=auth).json()["feedback_count"] == 1
    assert client.post(f"/predictions/{pid}/feedback", headers=auth, json={"kind": "nonsense"}).status_code == 422


def test_deleting_an_analysis_removes_its_files(client, auth, tmp_root):
    resp = upload(client, auth).json()
    pid = resp["prediction_id"]
    photo = tmp_root / "uploads" / resp["filename"]
    assert photo.is_file()
    assert client.delete(f"/predictions/{pid}", headers=auth).status_code == 204
    assert not photo.exists()
    assert client.get(f"/predictions/{pid}", headers=auth).status_code == 404


def test_access_is_audited(client):
    email = f"audit-{uuid.uuid4().hex[:8]}@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Audit Test",
                                   "confirms_professional_use": True})
    token = client.post("/login", json={"email": email, "password": "password123"}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    pid = upload(client, auth).json()["prediction_id"]
    client.get(f"/predictions/{pid}", headers=auth)
    client.get(f"/predictions/{pid}/image", headers=auth)
    client.delete(f"/predictions/{pid}", headers=auth)
    recorded = actions(email)
    for action in ("register", "login", "upload", "view", "view_photo", "delete"):
        assert action in recorded, action
    own = client.get("/me/audit", headers=auth).json()
    assert {e["action"] for e in own} >= {"upload", "delete"}


def test_retention_purge_deletes_old_analyses(client, auth, tmp_root):
    from datetime import timedelta

    from app.models import Prediction
    from app.services.prediction_service import PredictionService

    pid = upload(client, auth).json()["prediction_id"]
    with SessionLocal() as db:
        record = db.get(Prediction, pid)
        record.created_at = record.created_at - timedelta(days=400)
        db.commit()
        removed = PredictionService(db).purge_older_than(365)
    assert removed >= 1
    assert client.get(f"/predictions/{pid}", headers=auth).status_code == 404


# --- account security ---

def test_totp_matches_rfc_6238_test_vector():
    # RFC 6238 appendix B, SHA-1 secret "12345678901234567890", T = 59 s -> 94287082 (8 digits);
    # the 6-digit code is its last six digits.
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.verify(secret, "287082", now=59)
    assert not totp.verify(secret, "287083", now=59)


def test_two_factor_sign_in(client):
    email = f"mfa-{uuid.uuid4().hex[:8]}@clinic.org"
    reg = client.post("/register", json={"email": email, "password": "password123", "full_name": "Mfa Test",
                                         "confirms_professional_use": True}).json()
    auth = {"Authorization": f"Bearer {reg['access_token']}"}
    secret = client.post("/mfa/setup", headers=auth).json()["secret"]
    assert client.post("/mfa/enable", headers=auth, json={"code": "000000"}).status_code == 400
    now_code = totp.code_at(secret, int(time.time() // 30))
    assert client.post("/mfa/enable", headers=auth, json={"code": now_code}).json()["mfa_enabled"] is True

    needs_code = client.post("/login", json={"email": email, "password": "password123"})
    assert needs_code.status_code == 403
    wrong = client.post("/login", json={"email": email, "password": "password123", "mfa_code": "000000"})
    assert wrong.status_code == 401
    ok = client.post("/login", json={"email": email, "password": "password123",
                                     "mfa_code": totp.code_at(secret, int(time.time() // 30))})
    assert ok.status_code == 200


def test_invite_only_registration(client, monkeypatch):
    from app.services.auth_service import create_invite

    monkeypatch.setattr(settings, "REGISTRATION_MODE", "invite")
    base = {"password": "password123", "full_name": "Invited", "confirms_professional_use": True}
    assert client.post("/register", json={**base, "email": "no-code@clinic.org"}).status_code == 400
    with SessionLocal() as db:
        code = create_invite(db, email="invited@clinic.org")
    assert client.post("/register", json={**base, "email": "other@clinic.org", "invite_code": code}).status_code == 400
    assert client.post("/register", json={**base, "email": "invited@clinic.org", "invite_code": code}).status_code == 201
    # One use only.
    assert client.post("/register", json={**base, "email": "invited@clinic.org", "invite_code": code}).status_code == 400


def test_domain_restricted_registration(client, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_MODE", "domain")
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS", ["hospital.org"])
    base = {"password": "password123", "full_name": "Domain Test", "confirms_professional_use": True}
    assert client.post("/register", json={**base, "email": "x@gmail.com"}).status_code == 400
    assert client.post("/register", json={**base, "email": f"d{uuid.uuid4().hex[:6]}@hospital.org"}).status_code == 201


def test_password_reset_flow(client, monkeypatch):
    sent = []
    from app.routers import auth as auth_router
    monkeypatch.setattr(auth_router, "send_email", lambda to, subject, body: sent.append(body))
    email = f"reset-{uuid.uuid4().hex[:8]}@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Reset Test",
                                   "confirms_professional_use": True})
    # Unknown emails get the same answer and no email.
    assert client.post("/password-reset/request", json={"email": "nobody@clinic.org"}).status_code == 202
    assert sent == []
    assert client.post("/password-reset/request", json={"email": email}).status_code == 202
    token = sent[0].split("token=")[1].split()[0]
    assert client.post("/password-reset/confirm", json={"token": token, "new_password": "newpassword456"}).status_code == 200
    assert client.post("/login", json={"email": email, "password": "newpassword456"}).status_code == 200
    # The link works once.
    assert client.post("/password-reset/confirm", json={"token": token, "new_password": "another789x"}).status_code == 400


def test_public_config_reports_registration_mode(client):
    body = client.get("/config/public").json()
    assert body["registration_mode"] in {"open", "invite", "domain"}
    assert isinstance(body["password_reset_by_email"], bool)
