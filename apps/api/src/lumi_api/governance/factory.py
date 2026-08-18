from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Callable

from sqlalchemy.orm import Session

from .repository import PostgresGovernanceRepository
from .service import AuditExportPort, GovernanceService, ObjectDeletionPort, SearchDeletionPort


class PostgresGovernanceServiceFactory:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        object_deletion_port: ObjectDeletionPort | None = None,
        search_deletion_port: SearchDeletionPort | None = None,
        audit_export_port: AuditExportPort | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.object_deletion_port = object_deletion_port
        self.search_deletion_port = search_deletion_port
        self.audit_export_port = audit_export_port

    @contextmanager
    def __call__(self) -> Generator[GovernanceService, None, None]:
        session = self.session_factory()
        try:
            yield GovernanceService(
                PostgresGovernanceRepository(session),
                object_deletion_port=self.object_deletion_port,
                search_deletion_port=self.search_deletion_port,
                audit_export_port=self.audit_export_port,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
