from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import router as _router
from .notifications import AuthNotificationPort
from .secure_service import SecureAuthService


def create_auth_router(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    notifications: AuthNotificationPort,
    allowed_origins: frozenset[str],
    secure_cookie: bool = True,
):
    """Canonical public router factory.

    The lower-level router is transport plumbing; this binding forces every AuthService construction in
    its handlers through SecureAuthService, which adds privilege-escalation guards. NODE-17+ should
    import this factory, never `auth.router.create_auth_router` directly.
    """
    _router.AuthService = SecureAuthService
    return _router.create_auth_router(
        session_factory=session_factory,
        notifications=notifications,
        allowed_origins=allowed_origins,
        secure_cookie=secure_cookie,
    )
