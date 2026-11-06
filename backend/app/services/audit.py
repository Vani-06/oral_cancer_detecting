from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditEvent


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client else None


def record(db: Session, action: str, user_id: int | None = None, prediction_id: int | None = None,
           request: Request | None = None) -> None:
    """Appends one audit event and commits. Actions are short verbs such as
    login, upload, view, download_report, follow_up, feedback, delete."""
    db.add(AuditEvent(user_id=user_id, action=action, prediction_id=prediction_id, ip=client_ip(request)))
    db.commit()
