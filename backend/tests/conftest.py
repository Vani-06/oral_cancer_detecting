import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path

# Settings are read from the environment at import time, and backend/.env
# (pointing at the dev Postgres) is loaded without overriding variables that
# are already set -- so these must be set before anything imports `app`.
_TMP = Path(tempfile.mkdtemp(prefix="oral-cancer-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["REPORT_DIR"] = str(_TMP / "reports")
os.environ["MODEL_PATH"] = ""
os.environ["GRADING_MODEL_PATH"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402

VALID_METADATA = {
    "age": 52,
    "sex": "female",
    "tobacco_use": True,
    "tobacco_type": "smokeless",
    "tobacco_years": 10,
    "betel_quid_use": True,
    "alcohol_use": False,
    "lesion_site": "buccal_mucosa",
    "lesion_duration_weeks": 6,
    "pain": True,
    "bleeding": False,
    "prior_lesion_history": False,
}


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture(scope="session", autouse=True)
def _remove_tmp_root():
    # Each run writes test checkpoints (~90 MB each) here; without this the
    # folders piled up in the system temp directory until the disk filled.
    yield
    from app.db import engine

    engine.dispose()  # release the SQLite file so Windows lets us delete it
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def register(client: TestClient) -> dict[str, str]:
    email = f"user-{uuid.uuid4().hex[:10]}@clinic.org"
    resp = client.post(
        "/register",
        json={"email": email, "password": "password123", "full_name": "Test Clinician"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def auth(client) -> dict[str, str]:
    return register(client)


def jpeg_bytes(size=(320, 240), color=(180, 90, 90), exif_orientation: int | None = None) -> bytes:
    im = Image.new("RGB", size, color)
    buf = io.BytesIO()
    if exif_orientation is None:
        im.save(buf, format="JPEG")
    else:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        im.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()
