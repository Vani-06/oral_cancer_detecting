from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
