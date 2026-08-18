from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from .repository import PostgresApprovalRepository
from .service import ApprovalService


class PostgresApprovalServiceFactory:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def __call__(self, organization_id: UUID) -> Iterator[ApprovalService]:
        session = self.session_factory()
        try:
            yield ApprovalService(PostgresApprovalRepository(session, organization_id))
        finally:
            session.close()
