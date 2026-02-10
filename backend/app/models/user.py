from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)  # nullable for existing users
    email_verified = Column(Boolean, nullable=False, server_default="0")
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    password_change_code = Column(String(10), nullable=True)
    password_change_code_expires = Column(DateTime(timezone=True), nullable=True)
    # کد عددی تأیید ایمیل (انقضا دارد)
    verification_code = Column(String(10), nullable=True)
    verification_code_expires = Column(DateTime(timezone=True), nullable=True)
    # محدودیت درخواست کد: حداکثر ۳ بار، بعد قفل ۲ ساعته
    verification_code_request_count = Column(Integer, nullable=False, server_default="0")
    verification_code_locked_until = Column(DateTime(timezone=True), nullable=True)

    sessions = relationship("ChatSession", back_populates="user")

    def is_verification_code_valid(self, code: str) -> bool:
        if not self.verification_code or self.verification_code != code:
            return False
        if not self.verification_code_expires:
            return False
        exp = self.verification_code_expires
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def is_verification_request_locked(self) -> bool:
        """True if user cannot request a new code (within lock period)."""
        locked = self.verification_code_locked_until
        if not locked:
            return False
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        return locked > self._now_utc()

    def unlock_if_expired(self) -> None:
        """If lock period has passed, reset request count and clear lock."""
        locked = self.verification_code_locked_until
        if not locked:
            return
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if locked <= self._now_utc():
            self.verification_code_request_count = 0
            self.verification_code_locked_until = None

    def is_password_change_code_valid(self, code: str) -> bool:
        if not self.password_change_code or self.password_change_code != code:
            return False
        exp = self.password_change_code_expires
        if not exp:
            return False
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > self._now_utc()

