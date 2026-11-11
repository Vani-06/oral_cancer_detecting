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


def normalise_database_url(url: str) -> str:
    """Managed hosts (Render, Heroku-style) hand out postgres:// or
    postgresql:// URLs; SQLAlchemy needs the driver named, and this app
    ships psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


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

    DATABASE_URL: str = normalise_database_url(os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'oral_cancer.db'}"))
    AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

    # Optional: path to a trained resnet50_oral_cancer.pt checkpoint (see
    # ml/scripts/train.py). When unset or the file is missing, predictions
    # stay in the Pending state exactly as before real inference existed --
    # this is a deliberate fallback, not an error, so local dev and any
    # environment without the (large, model-specific) weights file keeps
    # working.
    MODEL_PATH: str | None = os.getenv("MODEL_PATH") or None
    # Optional: the dysplasia grading checkpoint (none / mild / moderate / severe,
    # see ml/scripts/train_grading.py). When unset, predictions carry no grade
    # but cancer detection still runs.
    GRADING_MODEL_PATH: str | None = os.getenv("GRADING_MODEL_PATH") or None
    # Optional: the "is this a clinical photo of the mouth?" check (see
    # ml/scripts/build_photo_gate.py). When set, uploads that don't look like
    # an oral photo -- a slide, a screenshot, a blank image -- are refused
    # instead of getting a Cancer / Non-Cancer result they can't support.
    GATE_MODEL_PATH: str | None = os.getenv("GATE_MODEL_PATH") or None
    # P(Cancer) at or above which a prediction is labelled Cancer. 0.5 is the
    # plain argmax; lower values trade more false alarms for fewer missed
    # cancers. Choose with the clinical team using the validation table in
    # ml/artifacts/model_card.md -- never by tuning against held-out data.
    CANCER_THRESHOLD: float = float(os.getenv("CANCER_THRESHOLD", "0.5"))
    # Three-way result (risk-controlled triage): the photo is re-scored under
    # 9 edits that should not change the diagnosis (STABILITY_EDITS) and the
    # mean P(cancer) decides: below TRIAGE_NO_CANCER_BELOW -> "no_cancer"; at
    # or above TRIAGE_CANCER_AT -> "cancer"; otherwise "inconclusive". The
    # lower threshold is set by conformal risk control on the validation split
    # so that at most 5% of cancers are expected to be called "no cancer";
    # the upper keeps non-cancers called "cancer" at or below 10%
    # (ml/scripts/conformal_triage.py). Corrected test split: 1.7% of cancers
    # called "no cancer", 81.8% of non-cancers cleared, 8.9% inconclusive.
    # Recalibrate whenever the model (MODEL_PATH) changes.
    # Abuse limits for public sign-up: registrations per client address and
    # analyses per account, each per rolling hour.
    # Who may sign up when ALLOW_REGISTRATION is on: "open" (anyone),
    # "invite" (one-time codes from backend/scripts/create_invite.py) or
    # "domain" (emails in ALLOWED_EMAIL_DOMAINS, e.g. a hospital domain).
    REGISTRATION_MODE: str = os.getenv("REGISTRATION_MODE", "open").lower()
    ALLOWED_EMAIL_DOMAINS: list[str] = [
        d.strip().lower() for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()
    ]
    # Analyses older than this are deleted with their files by
    # backend/scripts/purge_expired.py; 0 keeps them indefinitely.
    RETENTION_DAYS: int = int(os.getenv("RETENTION_DAYS", "0"))
    # Password reset by email. Without SMTP_HOST the link is written to the
    # server log, for development only.
    APP_URL: str = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
    PASSWORD_RESET_MINUTES: int = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    SMTP_HOST: str | None = os.getenv("SMTP_HOST") or None
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str | None = os.getenv("SMTP_USER") or None
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
    SMTP_FROM: str = os.getenv("SMTP_FROM", "no-reply@oralsentinel.local")
    REGISTER_MAX_PER_HOUR: int = int(os.getenv("REGISTER_MAX_PER_HOUR", "5"))
    PREDICT_MAX_PER_HOUR: int = int(os.getenv("PREDICT_MAX_PER_HOUR", "30"))
    # Temperature scaling of the cancer model's single-photo probability,
    # fitted on validation for v7 (ml/scripts/review_analyses.py: test ECE
    # 0.094 -> 0.070). Applies to the stored confidence only; the label
    # cut-off and the triage thresholds below use the uncalibrated scores
    # they were validated on. Refit when the model changes.
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "1.6226"))
    # Incident switch: refuse new analyses (503) while a serious problem is
    # investigated. Past results stay readable.
    ANALYSIS_PAUSED: bool = os.getenv("ANALYSIS_PAUSED", "false").lower() in {"1", "true", "yes"}
    TRIAGE_NO_CANCER_BELOW: float = float(os.getenv("TRIAGE_NO_CANCER_BELOW", "0.1447"))
    TRIAGE_CANCER_AT: float = float(os.getenv("TRIAGE_CANCER_AT", "0.4934"))
    # Same-patient reference: a lesion photo whose features are no further
    # from the patient's own opposite-side photo than this is not called
    # "cancer" outright (it becomes "inconclusive"). Provisional: 90th
    # percentile of left-half vs mirrored-right-half distance in healthy
    # photos (ml/scripts/asymmetry_experiment.py); recalibrate on paired
    # pilot photos.
    REFERENCE_SAME_AS_NORMAL_MAX: float = float(os.getenv("REFERENCE_SAME_AS_NORMAL_MAX", "0.56"))

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
    def analysis_version(self) -> str:
        """Which model files and triage thresholds produce results, stored
        with every analysis and printed on its report (traceability)."""
        stem = lambda v: Path(v).stem if v else "none"  # noqa: E731
        return (f"cancer={stem(self.MODEL_PATH)}; grade={stem(self.GRADING_MODEL_PATH)}; "
                f"gate={stem(self.GATE_MODEL_PATH)}; T={self.TEMPERATURE}; "
                f"triage={self.TRIAGE_NO_CANCER_BELOW}/{self.TRIAGE_CANCER_AT}")

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
        if self.REGISTRATION_MODE not in {"open", "invite", "domain"}:
            raise RuntimeError("REGISTRATION_MODE must be open, invite or domain")
        if self.REGISTRATION_MODE == "domain" and not self.ALLOWED_EMAIL_DOMAINS:
            raise RuntimeError("REGISTRATION_MODE=domain needs ALLOWED_EMAIL_DOMAINS")
        if not 0.05 <= self.TEMPERATURE <= 20:
            raise RuntimeError("TEMPERATURE must be between 0.05 and 20")
        if not 0.0 < self.TRIAGE_NO_CANCER_BELOW < self.TRIAGE_CANCER_AT <= 1.0:
            raise RuntimeError("Need 0 < TRIAGE_NO_CANCER_BELOW < TRIAGE_CANCER_AT <= 1")
        if self.is_production:
            # A deployed instance without its models would leave every
            # analysis "Pending" or skip the photo check; refuse to start.
            for name in ("MODEL_PATH", "GATE_MODEL_PATH", "GRADING_MODEL_PATH"):
                value = getattr(self, name)
                if not value or not Path(value).is_file():
                    raise RuntimeError(f"{name} must point to an existing model file in production")


settings = Settings()
