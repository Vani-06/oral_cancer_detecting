import pytest

from conftest import jpeg_bytes
from app.core.config import Settings, settings


def test_login_locks_out_after_repeated_failures(client):
    email = "lockout@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Lockout Test"})
    for _ in range(settings.LOGIN_MAX_FAILURES):
        assert client.post("/login", json={"email": email, "password": "wrong-pass"}).status_code == 401

    locked = client.post("/login", json={"email": email, "password": "password123"})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_successful_login_clears_failures(client):
    email = "reset@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Reset Test"})
    for _ in range(settings.LOGIN_MAX_FAILURES - 1):
        client.post("/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/login", json={"email": email, "password": "password123"}).status_code == 200
    assert client.post("/login", json={"email": email, "password": "wrong-pass"}).status_code == 401


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    resp = client.post("/register", json={"email": "x@clinic.org", "password": "password123", "full_name": "Blocked User"})
    assert resp.status_code == 403


@pytest.mark.parametrize("secret", ["dev-secret-change-in-production", "change-me", "short-but-unique"])
def test_production_rejects_weak_secret_keys(monkeypatch, secret):
    s = Settings()
    monkeypatch.setattr(s, "ENVIRONMENT", "production")
    monkeypatch.setattr(s, "SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        s.validate()


def test_production_accepts_a_strong_secret_key(monkeypatch):
    s = Settings()
    monkeypatch.setattr(s, "ENVIRONMENT", "production")
    monkeypatch.setattr(s, "SECRET_KEY", "k" * 48)
    s.validate()


def test_upload_rejects_non_image_bytes_with_image_extension(client, auth, tmp_root):
    before = set((tmp_root / "uploads").glob("*"))
    files = {"file": ("lesion.jpg", b"<script>alert(1)</script>", "image/jpeg")}
    resp = client.post("/predict", headers=auth, files=files)
    assert resp.status_code == 400
    assert "not a readable image" in resp.json()["detail"]
    assert set((tmp_root / "uploads").glob("*")) == before, "rejected file must not be kept"


def test_upload_accepts_a_real_image(client, auth):
    files = {"file": ("lesion.jpg", jpeg_bytes(), "image/jpeg")}
    assert client.post("/predict", headers=auth, files=files).status_code == 201


def test_responses_carry_security_headers(client):
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
