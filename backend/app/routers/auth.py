from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import LoginRateLimiter, SlidingWindowLimiter
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.prediction import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])

login_limiter = LoginRateLimiter(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_SECONDS)
register_limiter = SlidingWindowLimiter(settings.REGISTER_MAX_PER_HOUR, 3600)


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
        return service.register(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
        response = service.login(email=payload.email, password=payload.password)
    except ValueError as exc:
        login_limiter.record_failure(ip, payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    login_limiter.reset(ip, payload.email)
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)
