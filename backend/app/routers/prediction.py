import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.rate_limit import SlidingWindowLimiter
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models import Prediction, Report, User
from app.schemas.prediction import (
    FeedbackIn,
    FollowUpUpdate,
    PatientMetadata,
    PredictionDetail,
    PredictionHistoryItem,
    PredictionUploadResponse,
)
from app.services import audit
from app.services.prediction_service import PredictionService
from app.services.report_service import generate_report_pdf

router = APIRouter(tags=["predictions"])


def _report_url(record: Prediction) -> str | None:
    # A report is generated on demand by GET /reports/{id}, so it is available
    # as soon as the prediction itself is complete -- not only once a Report
    # row already exists (which only happens after the first download, and
    # the frontend disables the button when this is null).
    return None if record.is_pending else f"/reports/{record.prediction_id}"


# Generously above the largest valid record (the free-text fields allow
# ~3,000 characters); bounds the work json.loads does on hostile input.
_MAX_METADATA_CHARS = 20_000


def _parse_metadata(raw: str | None) -> dict | None:
    if not raw:
        return None
    if len(raw) > _MAX_METADATA_CHARS:
        raise ValueError("metadata_json is too large")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, RecursionError) as exc:
        # RecursionError: deeply nested input like "[[[[...]]]]" crashed the
        # request with a 500 before this was caught.
        raise ValueError("metadata_json must be valid JSON") from exc
    try:
        return PatientMetadata.model_validate(data).model_dump(exclude_none=True)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'metadata'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ValueError(f"Invalid patient metadata -- {problems}") from exc


def _image_url(record: Prediction) -> str | None:
    return f"/predictions/{record.prediction_id}/image" if record.filename else None


def _reference_image_url(record: Prediction) -> str | None:
    return f"/predictions/{record.prediction_id}/reference-image" if record.reference_filename else None


def _heatmap_url(record: Prediction) -> str | None:
    return f"/predictions/{record.prediction_id}/heatmap" if record.heatmap_path else None


def _private_file(path: Path, media_type: str | None = None) -> FileResponse:
    # Patient images must not be kept by shared caches or the browser's disk
    # cache after the clinician logs out.
    return FileResponse(str(path), media_type=media_type, headers={"Cache-Control": "private, no-store"})


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _record_to_detail(record: Prediction, feedback_count: int = 0) -> PredictionDetail:
    return PredictionDetail(
        follow_up=record.follow_up,
        follow_up_note=record.follow_up_note,
        follow_up_at=_iso(record.follow_up_at),
        consent_at=_iso(record.consent_at),
        feedback_count=feedback_count,
        prediction_id=record.prediction_id,
        prediction=record.prediction or "Pending",
        dysplasia_grade=record.dysplasia_grade,
        assessment=record.assessment,
        reference_status=record.reference_status,
        heatmap_url=_heatmap_url(record),
        pdf_url=_report_url(record),
        filename=record.filename,
        created_at=record.created_at.isoformat(),
        image_url=_image_url(record),
        reference_image_url=_reference_image_url(record),
        is_pending_inference=record.is_pending,
        model_version=record.model_version,
        metadata=record.metadata_json,
    )


def _record_to_history_item(record: Prediction) -> PredictionHistoryItem:
    return PredictionHistoryItem(
        prediction_id=record.prediction_id,
        prediction=record.prediction or "Pending",
        dysplasia_grade=record.dysplasia_grade,
        assessment=record.assessment,
        reference_status=record.reference_status,
        follow_up=record.follow_up,
        created_at=record.created_at.isoformat(),
        image_url=_image_url(record),
    )


predict_limiter = SlidingWindowLimiter(settings.PREDICT_MAX_PER_HOUR, 3600)


@router.post("/predict", response_model=PredictionUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_prediction(
    request: Request,
    file: UploadFile = File(...),
    metadata_json: str | None = Form(None),
    # Optional photo of the same site on the patient's healthy opposite side.
    reference_file: UploadFile | None = File(None),
    # The clinician confirms the patient consented to this analysis.
    consent_confirmed: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PredictionUploadResponse:
    if settings.ANALYSIS_PAUSED:
        # Incident switch (docs/incident-and-breach-response.md): no new
        # results while a serious problem is investigated; past results stay readable.
        raise HTTPException(status_code=503, detail="New analyses are paused while a problem is investigated. "
                                                    "Existing results and reports are still available.")
    retry_after = predict_limiter.hit(str(user.id))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many analyses in the last hour. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if not consent_confirmed:
        raise HTTPException(status_code=400, detail="Confirm that the patient has consented to this analysis.")
    service = PredictionService(db)
    try:
        metadata = _parse_metadata(metadata_json)
        prediction = service.create_prediction(
            user=user, file=file, metadata=metadata, reference_file=reference_file,
            consent_at=utcnow(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit.record(db, "upload", user_id=user.id, prediction_id=prediction.prediction_id, request=request)
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
        image_url=_image_url(prediction),
        reference_image_url=_reference_image_url(prediction),
        prediction=prediction.prediction or "Pending",
        dysplasia_grade=prediction.dysplasia_grade,
        assessment=prediction.assessment,
        reference_status=prediction.reference_status,
        heatmap_url=_heatmap_url(prediction),
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
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    audit.record(db, "view", user_id=user.id, prediction_id=prediction_id, request=request)
    return _record_to_detail(record, service.feedback_count(record))


@router.patch("/predictions/{prediction_id}/follow-up", response_model=PredictionDetail)
def update_follow_up(
    prediction_id: int,
    payload: FollowUpUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    service.set_follow_up(record, payload.status, payload.note)
    audit.record(db, f"follow_up_{payload.status}", user_id=user.id, prediction_id=prediction_id, request=request)
    return _record_to_detail(record, service.feedback_count(record))


@router.post("/predictions/{prediction_id}/feedback", status_code=status.HTTP_201_CREATED)
def report_wrong_result(
    prediction_id: int,
    payload: FeedbackIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    service.add_feedback(record, user, payload.kind, payload.actual_diagnosis, payload.comment)
    audit.record(db, "feedback", user_id=user.id, prediction_id=prediction_id, request=request)
    return {"detail": "Thank you. The report has been recorded for review."}


@router.delete("/predictions/{prediction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prediction(
    prediction_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    service.delete_prediction(record)
    audit.record(db, "delete", user_id=user.id, prediction_id=prediction_id, request=request)


@router.get("/predictions/{prediction_id}/image")
def get_prediction_image(
    prediction_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Replaces the old unauthenticated /uploads static mount: patient photos
    # are only served to the clinician who uploaded them.
    record = PredictionService(db).get_prediction(prediction_id, user)
    path = settings.UPLOAD_DIR / record.filename if record and record.filename else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    audit.record(db, "view_photo", user_id=user.id, prediction_id=prediction_id, request=request)
    return _private_file(path)


@router.get("/predictions/{prediction_id}/reference-image")
def get_prediction_reference_image(
    prediction_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = PredictionService(db).get_prediction(prediction_id, user)
    path = settings.UPLOAD_DIR / record.reference_filename if record and record.reference_filename else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Reference image not found")
    audit.record(db, "view_reference", user_id=user.id, prediction_id=prediction_id, request=request)
    return _private_file(path)


@router.get("/predictions/{prediction_id}/heatmap")
def get_prediction_heatmap(
    prediction_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = PredictionService(db).get_prediction(prediction_id, user)
    path = settings.UPLOAD_DIR / "heatmaps" / record.heatmap_path if record and record.heatmap_path else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Heatmap not found")
    audit.record(db, "view_heatmap", user_id=user.id, prediction_id=prediction_id, request=request)
    return _private_file(path, media_type="image/png")


@router.get("/reports/{prediction_id}")
def download_report(
    prediction_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PredictionService(db)
    record = service.get_prediction(prediction_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if record.is_pending:
        raise HTTPException(status_code=400, detail="Report not available until inference completes")
    audit.record(db, "download_report", user_id=user.id, prediction_id=prediction_id, request=request)

    # Reports are derived artifacts: always written to REPORT_DIR (outside the
    # image directory), and regenerated if the stored file is gone --
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
        headers={"Cache-Control": "private, no-store"},
    )
