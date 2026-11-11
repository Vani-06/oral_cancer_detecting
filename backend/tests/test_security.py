import pytest

from conftest import CONSENT, jpeg_bytes
from app.core.config import Settings, settings


def test_login_locks_out_after_repeated_failures(client):
    email = "lockout@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Lockout Test", "confirms_professional_use": True})
    for _ in range(settings.LOGIN_MAX_FAILURES):
        assert client.post("/login", json={"email": email, "password": "wrong-pass"}).status_code == 401

    locked = client.post("/login", json={"email": email, "password": "password123"})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_successful_login_clears_failures(client):
    email = "reset@clinic.org"
    client.post("/register", json={"email": email, "password": "password123", "full_name": "Reset Test", "confirms_professional_use": True})
    for _ in range(settings.LOGIN_MAX_FAILURES - 1):
        client.post("/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/login", json={"email": email, "password": "password123"}).status_code == 200
    assert client.post("/login", json={"email": email, "password": "wrong-pass"}).status_code == 401


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    resp = client.post("/register", json={"email": "x@clinic.org", "password": "password123", "full_name": "Blocked User", "confirms_professional_use": True})
    assert resp.status_code == 403


@pytest.mark.parametrize("secret", ["dev-secret-change-in-production", "change-me", "short-but-unique"])
def test_production_rejects_weak_secret_keys(monkeypatch, secret):
    s = Settings()
    monkeypatch.setattr(s, "ENVIRONMENT", "production")
    monkeypatch.setattr(s, "SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        s.validate()


def test_production_accepts_a_strong_secret_key(monkeypatch, tmp_path):
    s = Settings()
    monkeypatch.setattr(s, "ENVIRONMENT", "production")
    monkeypatch.setattr(s, "SECRET_KEY", "k" * 48)
    model = tmp_path / "model.pt"
    model.write_bytes(b"placeholder")
    for name in ("MODEL_PATH", "GATE_MODEL_PATH", "GRADING_MODEL_PATH"):
        monkeypatch.setattr(s, name, str(model))
    s.validate()


def test_upload_rejects_non_image_bytes_with_image_extension(client, auth, tmp_root):
    before = set((tmp_root / "uploads").glob("*"))
    files = {"file": ("lesion.jpg", b"<script>alert(1)</script>", "image/jpeg")}
    resp = client.post("/predict", headers=auth, files=files, data=CONSENT)
    assert resp.status_code == 400
    assert "not a readable image" in resp.json()["detail"]
    assert set((tmp_root / "uploads").glob("*")) == before, "rejected file must not be kept"


def test_upload_accepts_a_real_image(client, auth):
    files = {"file": ("lesion.jpg", jpeg_bytes(), "image/jpeg")}
    assert client.post("/predict", headers=auth, files=files, data=CONSENT).status_code == 201


def test_responses_carry_security_headers(client):
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"


def test_registration_requires_professional_confirmation(client):
    base = {"email": "consent@clinic.org", "password": "password123", "full_name": "No Consent"}
    assert client.post("/register", json=base).status_code == 422
    assert client.post("/register", json={**base, "confirms_professional_use": False}).status_code == 422


def test_registration_and_upload_limits(client, monkeypatch):
    from app.core.rate_limit import SlidingWindowLimiter
    from app.routers import auth as auth_router
    from app.routers import prediction as prediction_router

    monkeypatch.setattr(auth_router, "register_limiter", SlidingWindowLimiter(2, 3600))
    payload = lambda i: {"email": f"limit{i}@clinic.org", "password": "password123",  # noqa: E731
                         "full_name": "Limit Test", "confirms_professional_use": True}
    assert client.post("/register", json=payload(1)).status_code == 201
    assert client.post("/register", json=payload(2)).status_code == 201
    blocked = client.post("/register", json=payload(3))
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers

    monkeypatch.setattr(prediction_router, "predict_limiter", SlidingWindowLimiter(1, 3600))
    headers = {"Authorization": f"Bearer {client.post('/login', json={'email': 'limit1@clinic.org', 'password': 'password123'}).json()['access_token']}"}
    from conftest import jpeg_bytes
    files = lambda: {"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}  # noqa: E731
    assert client.post("/predict", headers=headers, files=files(), data=CONSENT).status_code == 201
    assert client.post("/predict", headers=headers, files=files(), data=CONSENT).status_code == 429


def test_production_refuses_to_start_without_models(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
    monkeypatch.setattr(settings, "MODEL_PATH", "")
    import pytest
    with pytest.raises(RuntimeError, match="MODEL_PATH"):
        settings.validate()


def test_managed_host_database_urls_get_the_psycopg_driver():
    from app.core.config import normalise_database_url

    assert normalise_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalise_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("sqlite:///./x.db") == "sqlite:///./x.db"
