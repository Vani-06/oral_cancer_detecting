import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models import Prediction, Report, User
from app.schemas.prediction import (
    PatientMetadata,
    PredictionDetail,
    PredictionHistoryItem,
    PredictionUploadResponse,
)
from app.services.prediction_service import PredictionService
from app.services.report_service import generate_report_pdf

router = APIRouter(tags=["predictions"])


def _report_url(record: Prediction) -> str | None:
    # A report is generated on demand by GET /reports/{id}, so it is available
    # as soon as the prediction itself is complete -- not only once a Report
    # row already exists (which only happens after the first download, and
    # the frontend disables the button when this is null).
    return None if record.is_pending else f"/reports/{record.prediction_id}"


def _parse_metadata(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("metadata_json must be valid JSON") from exc
    try:
        return PatientMetadata.model_validate(data).model_dump(exclude_none=True)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'metadata'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ValueError(f"Invalid patient metadata -- {problems}") from exc


def _record_to_detail(record: Prediction) -> PredictionDetail:
    return PredictionDetail(
        prediction_id=record.prediction_id,
        prediction=record.prediction or "Pending",
        confidence=record.confidence or 0.0,
        heatmap_url=f"/uploads/heatmaps/{record.heatmap_path}" if record.heatmap_path else None,
        pdf_url=_report_url(record),
        filename=record.filename,
        created_at=record.created_at.isoformat(),
        image_url=f"/uploads/{record.filename}" if record.filename else None,
        is_pending_inference=record.is_pending,
        metadata=record.metadata_json,
    )


def _record_to_history_item(record: Prediction) -> PredictionHistoryItem:
    return PredictionHistoryItem(
        prediction_id=record.prediction_id,
        prediction=record.prediction or "Pending",
        confidence=record.confidence or 0.0,
        created_at=record.created_at.isoformat(),
        image_url=f"/uploads/{record.filename}" if record.filename else None,
    )


@router.post("/predict", response_model=PredictionUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_prediction(
    file: UploadFile = File(...),
    metadata_json: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PredictionUploadResponse:
    service = PredictionService(db)
    try:
        metadata = _parse_metadata(metadata_json)
        prediction = service.create_prediction(user=user, file=file, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message = (
        "Image uploaded successfully. Inference is pending model configuration."
        if prediction.is_pending
        else "Image uploaded and analyzed successfully."
    )

    return PredictionUploadResponse(
        prediction_id=prediction.prediction_id,
        filename=prediction.filename,
        status="uploaded",
        message=message,
        created_at=prediction.created_at.isoformat(),
        image_url=f"/uploads/{prediction.filename}" if prediction.filename else None,
        prediction=prediction.prediction or "Pending",
        confidence=prediction.confidence or 0.0,
        heatmap_url=f"/uploads/heatmaps/{prediction.heatmap_path}" if prediction.heatmap_path else None,
        pdf_url=_report_url(prediction),
        is_pending_inference=prediction.is_pending,
    )


@router.get("/predictions", response_model=list[PredictionHistoryItem])
def list_predictions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    return [_record_to_history_item(record) for record in service.list_predictions(user)]


@router.get("/predictions/{prediction_id}", response_model=PredictionDetail)
def get_prediction(
    prediction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _record_to_detail(record)


@router.get("/reports/{prediction_id}")
def download_report(
    prediction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if record.is_pending:
        raise HTTPException(status_code=400, detail="Report not available until inference completes")

    # Reports are derived artifacts: always written to REPORT_DIR (outside the
    # public /uploads mount), and regenerated if the stored file is gone --
    # e.g. an ephemeral container filesystem, or a row created before reports
    # moved out of UPLOAD_DIR.
    report_path = Path(settings.REPORT_DIR) / f"{record.prediction_id}.pdf"
    if record.report is None or Path(record.report.pdf_path) != report_path or not report_path.is_file():
        generate_report_pdf(record, report_path)
        if record.report is None:
            record.report = Report(pdf_path=str(report_path))
        else:
            record.report.pdf_path = str(report_path)
        db.commit()

    return FileResponse(
        str(report_path),
        media_type="application/pdf",
        filename=f"oral-lesion-report-{record.prediction_id}.pdf",
    )
