import json
import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Populate os.environ from backend/.env for local (non-Docker) runs, e.g.
# `uvicorn` started directly from the venv. The class body below reads
# os.getenv(...) at class-definition time, so this must run first.
#
# Docker containers never have this file (the Dockerfile doesn't COPY it,
# and it's git-ignored) -- they get DATABASE_URL etc. from compose's
# `environment:`/`env_file:`, which populate os.environ before Python even
# starts. load_dotenv() does not override existing variables by default, so
# it's a no-op there rather than a conflicting second source of config.
load_dotenv(_BACKEND_DIR / ".env")


# Values shipped in this repo (defaults and .env.example). Anyone can read
# them, so a token signed with one can be forged.
_PLACEHOLDER_SECRETS = {"dev-secret-change-in-production", "change-me"}


class Settings:
    BASE_DIR: Path = _BACKEND_DIR
    APP_DIR: Path = BASE_DIR / "app"

    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(APP_DIR / "uploads")))
    # Kept apart from UPLOAD_DIR (which once was served publicly). Reports are
    # only reachable via the authenticated GET /reports/{id} endpoint, and
    # are regenerated if the file is missing, so this can be ephemeral.
    REPORT_DIR: Path = Path(os.getenv("REPORT_DIR", str(BASE_DIR / "reports")))
    ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()

    API_TITLE: str = os.getenv("API_TITLE", "Oral Cancer Detection API")
    API_VERSION: str = os.getenv("API_VERSION", "1.0.0")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # One clinic shift. The token sits in browser storage, so a shorter life
    # limits how long a stolen token stays useful.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # Open sign-up is convenient in development; in production accounts
    # should be created deliberately, so it defaults to off there.
    ALLOW_REGISTRATION: bool = os.getenv(
        "ALLOW_REGISTRATION", "false" if ENVIRONMENT == "production" else "true"
    ).lower() == "true"

    # Failed logins allowed per (IP, email) within the window before a 429.
    LOGIN_MAX_FAILURES: int = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    LOGIN_WINDOW_SECONDS: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'oral_cancer.db'}")
    AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

    # Optional: path to a trained resnet50_oral_cancer.pt checkpoint (see
    # ml/scripts/train.py). When unset or the file is missing, predictions
    # stay in the Pending state exactly as before real inference existed --
    # this is a deliberate fallback, not an error, so local dev and any
    # environment without the (large, model-specific) weights file keeps
    # working.
    MODEL_PATH: str | None = os.getenv("MODEL_PATH") or None
    # Optional: the dysplasia grading checkpoint (mild / moderate / severe,
    # see ml/scripts/train_grading.py). When unset, predictions carry no grade
    # but cancer detection still runs.
    GRADING_MODEL_PATH: str | None = os.getenv("GRADING_MODEL_PATH") or None
    # P(Cancer) at or above which a prediction is labelled Cancer. 0.5 is the
    # plain argmax; lower values trade more false alarms for fewer missed
    # cancers. Choose with the clinical team using the validation table in
    # ml/artifacts/model_card.md -- never by tuning against held-out data.
    CANCER_THRESHOLD: float = float(os.getenv("CANCER_THRESHOLD", "0.5"))

    CORS_ORIGINS_RAW: str = os.getenv(
        "CORS_ORIGINS",
        '["http://localhost:5173", "http://localhost:3000"]',
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS_RAW.strip()
        if raw.startswith("["):
            return json.loads(raw)
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate(self) -> None:
        if self.is_production and (
            self.SECRET_KEY in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32
        ):
            raise RuntimeError(
                "SECRET_KEY must be a random value of at least 32 characters in production "
                '(e.g. python -c "import secrets; print(secrets.token_urlsafe(48))")'
            )
        if self.MAX_FILE_SIZE_MB <= 0:
            raise RuntimeError("MAX_FILE_SIZE_MB must be positive")
        if not 0.0 < self.CANCER_THRESHOLD < 1.0:
            raise RuntimeError("CANCER_THRESHOLD must be strictly between 0 and 1")


settings = Settings()
