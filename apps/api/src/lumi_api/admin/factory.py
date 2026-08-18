from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from .contracts import DeadLetterReplayPort, PlatformAdminForbidden
from .repository_safe import PostgresPlatformAdminRepository
from .service import PlatformAdminService


class PostgresPlatformAdminServiceFactory:
    def __init__(self, session_factory: Callable[[], Session], replay_port: DeadLetterReplayPort | None = None) -> None:
        self.session_factory = session_factory
        self.replay_port = replay_port

    @contextmanager
    def __call__(self, user_id: UUID) -> Iterator[PlatformAdminService]:
        session = self.session_factory()
        try:
            repository = PostgresPlatformAdminRepository(session)
            principal = repository.principal_for_user(user_id)
            if principal is None:
                raise PlatformAdminForbidden("PLATFORM_ADMIN_PRINCIPAL_REQUIRED")
            yield PlatformAdminService(repository, principal, self.replay_port)
        finally:
            session.close()
