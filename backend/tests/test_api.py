import json

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
