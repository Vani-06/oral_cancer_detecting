from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
import json
from pathlib import Path
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.models import Prediction, Report, User
from app.schemas.prediction import PredictionDetail, PredictionHistoryItem, PredictionUploadResponse
from app.services.prediction_service import PredictionService

router = APIRouter(tags=["predictions"])


def _record_to_detail(record: Prediction) -> PredictionDetail:
    return PredictionDetail(
        prediction_id=record.prediction_id,
        prediction=record.prediction or "Pending",
        confidence=record.confidence or 0.0,
        heatmap_url=f"/uploads/heatmaps/{record.heatmap_path}" if record.heatmap_path else None,
        pdf_url=f"/reports/{record.prediction_id}" if record.report else None,
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
        metadata = None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as exc:
                raise ValueError("metadata_json must be valid JSON") from exc
            if not isinstance(metadata, dict):
                raise ValueError("metadata_json must contain a JSON object")
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
    if record.report is None:
        report_dir = Path(settings.UPLOAD_DIR) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{record.prediction_id}.pdf"
        # Keep report generation dependency-free. This is a plain PDF with a
        # clear non-diagnostic disclaimer until clinical reporting is reviewed.
        lines = [
            "Oral lesion analysis report",
            f"Prediction: {record.prediction or 'Pending'}",
            f"Confidence: {record.confidence or 0:.2f}",
            "This software is an investigational aid, not a diagnosis.",
            "Clinical examination and histopathology remain required.",
        ]
        content = "BT\n/F1 12 Tf\n72 740 Td\n" + "\n".join(
            f"({line.replace('(', '[').replace(')', ']')}) Tj 0 -22 Td" for line in lines
        ) + "\nET"
        objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        pdf = "%PDF-1.4\n"
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(pdf.encode()))
            pdf += f"{index} 0 obj\n{obj}\nendobj\n"
        xref = len(pdf.encode())
        pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
        pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
        pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
        report_path.write_bytes(pdf.encode())
        record.report = Report(pdf_path=str(report_path))
        db.commit()
    report_path = Path(record.report.pdf_path)
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(str(report_path), media_type="application/pdf", filename=report_path.name)
