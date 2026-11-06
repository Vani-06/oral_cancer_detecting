import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import totp
from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Invite, User
from app.schemas.prediction import AuthResponse, UserResponse

# Checked when the email is unknown, so a failed login takes the same bcrypt
# time either way and response timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


class MfaRequired(Exception):
    """Password was right but the account needs a valid authenticator code."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, email: str, full_name: str, password: str, invite_code: str | None = None) -> AuthResponse:
        normalized_email = email.lower()
        invite = self._check_registration_allowed(normalized_email, invite_code)
        existing_user = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing_user is not None:
            raise ValueError("Email already registered")

        user = User(
            email=normalized_email,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        self.db.add(user)
        if invite is not None:
            invite.used_at = utcnow()
        self.db.commit()
        self.db.refresh(user)
        return self._build_auth_response(user)

    def _check_registration_allowed(self, email: str, invite_code: str | None) -> Invite | None:
        mode = settings.REGISTRATION_MODE
        if mode == "domain":
            domain = email.rsplit("@", 1)[-1]
            if domain not in settings.ALLOWED_EMAIL_DOMAINS:
                raise ValueError("Sign-up is limited to approved institutional email addresses.")
        if mode != "invite":
            return None
        if not invite_code:
            raise ValueError("An invitation code is required to sign up.")
        invite = self.db.scalar(select(Invite).where(Invite.code_hash == _sha256(invite_code.strip())))
        if invite is None or invite.used_at is not None or invite.expires_at < utcnow():
            raise ValueError("This invitation code is invalid, used or expired.")
        if invite.email and invite.email.lower() != email:
            raise ValueError("This invitation code was issued for a different email address.")
        return invite

    def login(self, email: str, password: str, mfa_code: str | None = None) -> AuthResponse:
        normalized_email = email.lower()
        user = self.db.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise ValueError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        if user.mfa_enabled:
            if not mfa_code:
                raise MfaRequired()
            if not totp.verify(user.mfa_secret or "", mfa_code):
                raise ValueError("Invalid authentication code")
        return self._build_auth_response(user)

    # --- two-factor sign-in ---

    def start_mfa_setup(self, user: User) -> tuple[str, str]:
        if user.mfa_enabled:
            raise ValueError("Two-factor sign-in is already on.")
        user.mfa_secret = totp.new_secret()
        self.db.commit()
        return user.mfa_secret, totp.provisioning_uri(user.mfa_secret, user.email)

    def enable_mfa(self, user: User, code: str) -> None:
        if not user.mfa_secret or not totp.verify(user.mfa_secret, code):
            raise ValueError("That code did not match. Check the time on your phone and try again.")
        user.mfa_enabled = True
        self.db.commit()

    def disable_mfa(self, user: User, code: str, password: str) -> None:
        if not verify_password(password, user.password_hash) or not totp.verify(user.mfa_secret or "", code):
            raise ValueError("Password or authentication code is wrong.")
        user.mfa_enabled = False
        user.mfa_secret = None
        self.db.commit()

    # --- password reset ---

    def create_reset_token(self, email: str) -> tuple[User, str] | None:
        """Returns (user, token) for a known email, else None. Only the
        token's hash is stored."""
        user = self.db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            return None
        token = secrets.token_urlsafe(32)
        user.password_reset_hash = _sha256(token)
        user.password_reset_expires = utcnow() + timedelta(minutes=settings.PASSWORD_RESET_MINUTES)
        self.db.commit()
        return user, token

    def reset_password(self, token: str, new_password: str) -> User:
        user = self.db.scalar(select(User).where(User.password_reset_hash == _sha256(token)))
        if user is None or user.password_reset_expires is None or user.password_reset_expires < utcnow():
            raise ValueError("This reset link is invalid or has expired.")
        user.password_hash = hash_password(new_password)
        user.password_reset_hash = None
        user.password_reset_expires = None
        self.db.commit()
        return user

    def _build_auth_response(self, user: User) -> AuthResponse:
        token = create_access_token(user.id)
        return AuthResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )


def create_invite(db: Session, email: str | None = None, days: int = 14) -> str:
    """Creates a one-time invitation code; returns the code (stored hashed)."""
    code = secrets.token_urlsafe(12)
    db.add(Invite(code_hash=_sha256(code), email=email.lower() if email else None,
                  expires_at=utcnow() + timedelta(days=days)))
    db.commit()
    return code
