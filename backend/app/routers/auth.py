from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.mail import send_email
from app.core.rate_limit import LoginRateLimiter, SlidingWindowLimiter
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models import AuditEvent, User
from app.schemas.prediction import (
    AuditEventOut,
    AuthResponse,
    LoginRequest,
    MfaCode,
    MfaDisable,
    MfaSetupResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PublicConfig,
    RegisterRequest,
    UserResponse,
)
from app.services import audit
from app.services.auth_service import AuthService, MfaRequired

router = APIRouter(tags=["auth"])

login_limiter = LoginRateLimiter(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_SECONDS)
register_limiter = SlidingWindowLimiter(settings.REGISTER_MAX_PER_HOUR, 3600)
reset_limiter = SlidingWindowLimiter(5, 3600)

MFA_REQUIRED_DETAIL = "Enter the 6-digit code from your authenticator app."


def _reset_by_email_available() -> bool:
    # Without SMTP, development logs the link; production refuses rather
    # than write reset links to its logs.
    return bool(settings.SMTP_HOST) or not settings.is_production


@router.get("/config/public", response_model=PublicConfig)
def public_config():
    return PublicConfig(
        allow_registration=settings.ALLOW_REGISTRATION,
        registration_mode=settings.REGISTRATION_MODE,
        password_reset_by_email=_reset_by_email_available(),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled. Ask an administrator for an account.",
        )
    retry_after = register_limiter.hit(request.client.host if request.client else "unknown")
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many accounts created from this network. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    service = AuthService(db)
    try:
        response = service.register(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            invite_code=payload.invite_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit.record(db, "register", user_id=response.user.id, request=request)
    return response


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    retry_after = login_limiter.retry_after(ip, payload.email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    service = AuthService(db)
    try:
        response = service.login(email=payload.email, password=payload.password, mfa_code=payload.mfa_code)
    except MfaRequired as exc:
        # Distinct status so the sign-in page can ask for the code; not a failure.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MFA_REQUIRED_DETAIL) from exc
    except ValueError as exc:
        login_limiter.record_failure(ip, payload.email)
        audit.record(db, "login_failed", request=request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    login_limiter.reset(ip, payload.email)
    audit.record(db, "login", user_id=response.user.id, request=request)
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/me/audit", response_model=list[AuditEventOut])
def my_audit_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The signed-in clinician's own access history (latest 200 events)."""
    stmt = select(AuditEvent).where(AuditEvent.user_id == user.id).order_by(desc(AuditEvent.id)).limit(200)
    return list(db.scalars(stmt).all())


# --- two-factor sign-in ---

@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        secret, uri = AuthService(db).start_mfa_setup(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=UserResponse)
def mfa_enable(payload: MfaCode, request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    try:
        AuthService(db).enable_mfa(user, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(db, "mfa_enabled", user_id=user.id, request=request)
    return UserResponse.model_validate(user)


@router.post("/mfa/disable", response_model=UserResponse)
def mfa_disable(payload: MfaDisable, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    try:
        AuthService(db).disable_mfa(user, payload.code, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(db, "mfa_disabled", user_id=user.id, request=request)
    return UserResponse.model_validate(user)


# --- password reset ---

@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    if not _reset_by_email_available():
        raise HTTPException(status_code=503, detail="Password reset by email is not set up. Ask an administrator.")
    if reset_limiter.hit(request.client.host if request.client else "unknown") is not None:
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again later.")
    created = AuthService(db).create_reset_token(payload.email)
    if created is not None:
        user, token = created
        link = f"{settings.APP_URL}/reset-password?token={token}"
        send_email(user.email, "OralSentinel password reset",
                   f"Use this link within {settings.PASSWORD_RESET_MINUTES} minutes to set a new password:\n\n"
                   f"{link}\n\nIf you did not ask for this, ignore this email.")
        audit.record(db, "password_reset_requested", user_id=user.id, request=request)
    # Same answer whether or not the email exists, so accounts cannot be probed.
    return {"detail": "If that email has an account, a reset link has been sent."}


@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    try:
        user = AuthService(db).reset_password(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(db, "password_reset", user_id=user.id, request=request)
    return {"detail": "Password updated. You can sign in now."}
