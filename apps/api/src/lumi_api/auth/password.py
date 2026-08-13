from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


class Argon2idPasswordService:
    """Thin adapter over argon2-cffi; no custom password crypto is implemented by LUMI."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(type=Type.ID)

    def hash_password(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str, candidate: str) -> bool:
        try:
            return bool(self._hasher.verify(password_hash, candidate))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (VerificationError, InvalidHashError):
            return True
