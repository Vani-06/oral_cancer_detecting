from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.prediction import AuthResponse, UserResponse

# Checked when the email is unknown, so a failed login takes the same bcrypt
# time either way and response timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, email: str, full_name: str, password: str) -> AuthResponse:
        normalized_email = email.lower()
        existing_user = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing_user is not None:
            raise ValueError("Email already registered")

        user = User(
            email=normalized_email,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._build_auth_response(user)

    def login(self, email: str, password: str) -> AuthResponse:
        normalized_email = email.lower()
        user = self.db.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise ValueError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        return self._build_auth_response(user)

    def _build_auth_response(self, user: User) -> AuthResponse:
        token = create_access_token(user.id)
        return AuthResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
