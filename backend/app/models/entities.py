from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Two-factor sign-in (TOTP). The secret is set at setup and only used
    # once mfa_enabled is true.
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # Password reset: SHA-256 of the one-time token, never the token itself.
    password_reset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    prediction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Kept for audit and model evaluation; never sent to clients.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    dysplasia_grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    heatmap_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional photo of the same patient's healthy opposite-side site.
    reference_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "used", or "not_normal" when the reference itself looked abnormal and
    # the assessment fell back to the lesion photo alone; None = no reference.
    reference_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # "cancer" / "no_cancer" / "inconclusive" (retake or refer).
    assessment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Models and thresholds that produced this result (settings.analysis_version).
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Referral workflow for "cancer" and "inconclusive" results:
    # needed -> referred / retake_requested -> closed.
    follow_up: Mapped[str | None] = mapped_column(String(24), nullable=True)
    follow_up_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    # When the uploading clinician confirmed the patient's consent.
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="predictions")
    report: Mapped["Report | None"] = relationship(
        back_populates="prediction",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def is_pending(self) -> bool:
        return self.prediction is None


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.prediction_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    prediction: Mapped[Prediction] = relationship(back_populates="report")


class AuditEvent(Base):
    """Who did what, when: sign-ins, uploads, views, downloads, changes."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    prediction_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())


class ResultFeedback(Base):
    """A clinician's report that a result was wrong."""

    __tablename__ = "result_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    actual_diagnosis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())


class Invite(Base):
    """One-time sign-up code for invite-only registration."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
