from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Callable

from sqlalchemy.orm import Session

from .repository import PostgresGovernanceRepository
from .service import (
    AuditExportPort,
    GovernanceService,
    ObjectDeletionPort,
    SearchDeletionPort,
    SubjectDeactivationPort,
)


class PostgresGovernanceServiceFactory:
    """Request-scoped transactional Governance service factory.

    HTTP governance mutations and their mandatory audit events commit together. Production
    deletion/export workers remain separately composed P0 work because their external side
    effects require idempotent durable worker semantics rather than a browser request.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        subject_deactivation_port: SubjectDeactivationPort | None = None,
        object_deletion_port: ObjectDeletionPort | None = None,
        search_deletion_port: SearchDeletionPort | None = None,
        audit_export_port: AuditExportPort | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.subject_deactivation_port = subject_deactivation_port
        self.object_deletion_port = object_deletion_port
        self.search_deletion_port = search_deletion_port
        self.audit_export_port = audit_export_port

    @contextmanager
    def __call__(self) -> Generator[GovernanceService, None, None]:
        session = self.session_factory()
        try:
            with session.begin():
                yield GovernanceService(
                    PostgresGovernanceRepository(session),
                    subject_deactivation_port=self.subject_deactivation_port,
                    object_deletion_port=self.object_deletion_port,
                    search_deletion_port=self.search_deletion_port,
                    audit_export_port=self.audit_export_port,
                )
        finally:
            session.close()
