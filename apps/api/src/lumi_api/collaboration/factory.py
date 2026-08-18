from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from .presence import PresencePort
from .repository import PostgresCollaborationRepository
from .service import CollaborationService


class PostgresCollaborationServiceFactory:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        presence: PresencePort,
    ) -> None:
        self.session_factory = session_factory
        self.presence = presence

    @contextmanager
    def __call__(self, organization_id: UUID) -> Iterator[CollaborationService]:
        session = self.session_factory()
        try:
            repository = PostgresCollaborationRepository(session, organization_id)
            yield CollaborationService(repository, self.presence)
        finally:
            session.close()
