from __future__ import annotations

from typing import Protocol


class AuthNotificationPort(Protocol):
    async def send_email_verification(self, *, email: str, token: str) -> None: ...
    async def send_password_reset(self, *, email: str, token: str) -> None: ...
    async def send_organization_invite(
        self,
        *,
        email: str,
        organization_id: str,
        token: str,
    ) -> None: ...


class AuthNotificationNotConfigured(RuntimeError):
    pass


class RejectingAuthNotificationPort:
    """Production-safe default: never leak token by logging or HTTP response."""

    async def send_email_verification(self, *, email: str, token: str) -> None:
        raise AuthNotificationNotConfigured("email verification delivery is not configured")

    async def send_password_reset(self, *, email: str, token: str) -> None:
        raise AuthNotificationNotConfigured("password reset delivery is not configured")

    async def send_organization_invite(
        self,
        *,
        email: str,
        organization_id: str,
        token: str,
    ) -> None:
        raise AuthNotificationNotConfigured("organization invite delivery is not configured")
