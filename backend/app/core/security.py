"""JWT and password hashing."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    VERIFICATION_TOKEN_EXPIRE_MINUTES,
    VERIFICATION_CODE_LENGTH,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_verification_token(email: str, username: str) -> str:
    """Short-lived token for email verification (e.g. 24h)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": username, "email": email, "type": "email_verify", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_verification_token(token: str) -> dict[str, Any] | None:
    """Decode email verification token; returns None if invalid or expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "email_verify":
            return None
        return payload
    except JWTError:
        return None


def create_email_change_token(username: str, new_email: str) -> str:
    """Token for confirming new email address (e.g. 24h)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": username, "new_email": new_email, "type": "email_change", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_email_change_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "email_change":
            return None
        return payload
    except JWTError:
        return None


def generate_verification_code() -> str:
    """Generate a numeric verification code (e.g. 6 digits)."""
    return "".join(secrets.choice("0123456789") for _ in range(VERIFICATION_CODE_LENGTH))
