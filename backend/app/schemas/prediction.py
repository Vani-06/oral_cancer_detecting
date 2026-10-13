from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Auth schemas ---

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# --- Prediction schemas ---

class PatientMetadata(BaseModel):
    """Server-side mirror of frontend/src/lib/metadataSchema.ts.

    The frontend validates too, but the API is the boundary: without this,
    any JSON object posted as metadata_json was stored as-is and printed into
    the PDF report. Field names and ranges must stay identical to the
    frontend schema and to PatientMetadata in frontend/src/api/types.ts.
    """

    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=1, le=120)
    sex: Literal["male", "female", "other"]
    tobacco_use: bool
    tobacco_type: Literal["smoked", "smokeless", "both"] | None = None
    tobacco_years: int | None = Field(default=None, ge=0, le=100)
    betel_quid_use: bool
    alcohol_use: bool
    lesion_site: Literal[
        "buccal_mucosa", "tongue", "gingiva", "palate", "floor_of_mouth", "lip"
    ]
    lesion_duration_weeks: int = Field(ge=0, le=520)
    pain: bool
    bleeding: bool
    prior_lesion_history: bool

    @model_validator(mode="after")
    def tobacco_follow_ups(self) -> "PatientMetadata":
        if self.tobacco_use and (self.tobacco_type is None or self.tobacco_years is None):
            raise ValueError("tobacco_type and tobacco_years are required when tobacco_use is true")
        return self


class PredictionUploadResponse(BaseModel):
    """Response returned after successfully uploading an image."""

    prediction_id: int
    filename: str
    status: str
    message: str
    created_at: str
    image_url: str | None = None
    prediction: str = "Pending"
    confidence: float = 0.0
    heatmap_url: str | None = None
    pdf_url: str | None = None
    is_pending_inference: bool = True


class PredictionResult(BaseModel):
    """Full prediction result (used once ML inference is integrated)."""

    prediction_id: int
    prediction: str
    confidence: float
    heatmap_url: str | None = None
    pdf_url: str | None = None


class PredictionHistoryItem(BaseModel):
    """A single entry in prediction history."""

    prediction_id: int
    prediction: str
    confidence: float
    created_at: str
    image_url: str | None = None


class PredictionDetail(BaseModel):
    """Detailed prediction for GET /predictions/{id} - matches frontend PredictionOutcome."""

    prediction_id: int
    prediction: str
    confidence: float
    heatmap_url: str | None = None
    pdf_url: str | None = None
    filename: str
    created_at: str
    image_url: str | None = None
    is_pending_inference: bool
    metadata: dict | None = None
