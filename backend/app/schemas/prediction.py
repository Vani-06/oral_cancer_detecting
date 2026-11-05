from datetime import datetime
from typing import Literal

# Model scores are deliberately never part of any response: the app reports a
# grade and a detection result, not a probability a clinician might over-read.
DysplasiaGrade = Literal["none", "mild", "moderate", "severe"]
Assessment = Literal["cancer", "no_cancer", "inconclusive"]
ReferenceStatus = Literal["used", "not_normal"]

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Auth schemas ---

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    # Open sign-up: the user confirms they are a health professional with
    # the patient's consent to upload photos. Must be true.
    confirms_professional_use: Literal[True]

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

    The optional free-text and duration fields mirror the columns of the
    client's own case sheet (patient ID, habit duration, medical history,
    clinical notes), so a case recorded there can be entered here unchanged.
    """

    # strict: the frontend sends real JSON numbers and booleans, so 1/0 for
    # yes/no or true for a number of years is a malformed request, not data.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    patient_reference: str | None = Field(default=None, max_length=64)
    age: int = Field(ge=1, le=120)
    sex: Literal["male", "female", "other"]
    tobacco_use: bool
    tobacco_type: Literal["smoked", "smokeless", "both"] | None = None
    tobacco_years: int | None = Field(default=None, ge=0, le=100)
    betel_quid_use: bool
    betel_quid_years: int | None = Field(default=None, ge=0, le=100)
    alcohol_use: bool
    # Optional: which side the lesion and the habit are on. A lesion on the
    # side where the patient holds pan / tobacco is reported as concordant.
    lesion_side: Literal["left", "right", "midline"] | None = None
    habit_side: Literal["left", "right", "both"] | None = None
    lesion_site: Literal[
        "buccal_mucosa",
        "tongue",
        "gingiva",
        "palate",
        "floor_of_mouth",
        "lip",
        "retromolar_trigone",
        "alveolar_ridge",
        "other",
    ]
    # Optional: the client's case sheet does not record it for most patients.
    lesion_duration_weeks: int | None = Field(default=None, ge=0, le=520)
    pain: bool
    bleeding: bool
    prior_lesion_history: bool
    medical_history: str | None = Field(default=None, max_length=1000)
    clinical_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("patient_reference", "medical_history", "clinical_notes")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return v or None

    @model_validator(mode="after")
    def consistent_history(self) -> "PatientMetadata":
        if self.tobacco_use and (self.tobacco_type is None or self.tobacco_years is None):
            raise ValueError("tobacco_type and tobacco_years are required when tobacco_use is true")
        # Follow-ups to a habit answered "no" are leftovers (the form hides
        # them but may still send them); drop them so the record and the PDF
        # never say "no tobacco, 15 years of tobacco".
        if not self.tobacco_use:
            self.tobacco_type = self.tobacco_years = None
        if not self.betel_quid_use:
            self.betel_quid_years = None
        for field in ("tobacco_years", "betel_quid_years"):
            years = getattr(self, field)
            if years is not None and years > self.age:
                raise ValueError(f"{field} ({years}) cannot exceed the patient's age ({self.age})")
        if self.lesion_duration_weeks is not None and self.lesion_duration_weeks > (self.age + 1) * 52:
            raise ValueError("lesion_duration_weeks cannot exceed the patient's age")
        return self


class PredictionUploadResponse(BaseModel):
    """Response returned after successfully uploading an image."""

    prediction_id: int
    filename: str
    status: str
    message: str
    created_at: str
    image_url: str | None = None
    reference_image_url: str | None = None
    prediction: str = "Pending"
    dysplasia_grade: DysplasiaGrade | None = None
    assessment: Assessment | None = None
    reference_status: ReferenceStatus | None = None
    heatmap_url: str | None = None
    pdf_url: str | None = None
    is_pending_inference: bool = True


class PredictionResult(BaseModel):
    """Full prediction result (used once ML inference is integrated)."""

    prediction_id: int
    prediction: str
    dysplasia_grade: DysplasiaGrade | None = None
    assessment: Assessment | None = None
    reference_status: ReferenceStatus | None = None
    heatmap_url: str | None = None
    pdf_url: str | None = None


class PredictionHistoryItem(BaseModel):
    """A single entry in prediction history."""

    prediction_id: int
    prediction: str
    dysplasia_grade: DysplasiaGrade | None = None
    assessment: Assessment | None = None
    reference_status: ReferenceStatus | None = None
    created_at: str
    image_url: str | None = None


class PredictionDetail(BaseModel):
    """Detailed prediction for GET /predictions/{id} - matches frontend PredictionOutcome."""

    prediction_id: int
    prediction: str
    dysplasia_grade: DysplasiaGrade | None = None
    assessment: Assessment | None = None
    reference_status: ReferenceStatus | None = None
    heatmap_url: str | None = None
    pdf_url: str | None = None
    filename: str
    created_at: str
    image_url: str | None = None
    reference_image_url: str | None = None
    is_pending_inference: bool
    metadata: dict | None = None
    model_version: str | None = None
