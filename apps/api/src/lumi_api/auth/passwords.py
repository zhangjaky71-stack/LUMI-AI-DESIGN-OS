from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, encoded_hash: str, password: str) -> bool: ...


class PasswordHasherUnavailable(RuntimeError):
    pass


class Argon2idPasswordHasher:
    """Thin adapter over argon2-cffi.

    The cryptographic implementation remains owned by argon2-cffi. This module
    intentionally does not implement Argon2 itself. The import is lazy so the
    NODE-16 contract can be linted and type-checked before the locked workspace
    dependency is added by a forward dependency update.
    """

    def __init__(self) -> None:
        try:
            module = import_module("argon2")
        except ModuleNotFoundError as exc:
            raise PasswordHasherUnavailable(
                "argon2-cffi is required for production password hashing"
            ) from exc
        password_hasher_type: Any = getattr(module, "PasswordHasher")
        profiles: Any = getattr(module, "profiles", None)
        if profiles is not None and hasattr(profiles, "RFC_9106_LOW_MEMORY"):
            self._hasher = password_hasher_type.from_parameters(
                profiles.RFC_9106_LOW_MEMORY
            )
        else:
            self._hasher = password_hasher_type(type=getattr(module, "Type").ID)

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        encoded = str(self._hasher.hash(password))
        if not encoded.startswith("$argon2id$"):
            raise RuntimeError("password library did not emit Argon2id")
        return encoded

    def verify(self, encoded_hash: str, password: str) -> bool:
        if not encoded_hash.startswith("$argon2id$"):
            return False
        try:
            return bool(self._hasher.verify(encoded_hash, password))
        except Exception as exc:  # library exposes dedicated mismatch exceptions
            name = type(exc).__name__
            if name in {"VerifyMismatchError", "VerificationError", "InvalidHashError"}:
                return False
            raise


def validate_password_policy(password: str) -> None:
    if len(password) < 12:
        raise ValueError("PASSWORD_TOO_SHORT")
    if len(password) > 1024:
        raise ValueError("PASSWORD_TOO_LONG")
