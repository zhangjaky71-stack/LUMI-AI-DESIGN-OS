from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, Self

from lumi_domain import DomainEvent
from lumi_domain.ports import (
    AgentRunRepository,
    ArtifactRepository,
    AssetRepository,
    CostLedgerRepository,
    ProjectRepository,
    TaskRepository,
)

from .context import ApplicationContext


class DomainEventOutbox(Protocol):
    async def append(self, event: DomainEvent) -> None: ...


class ApplicationUnitOfWork(Protocol):
    projects: ProjectRepository
    assets: AssetRepository
    artifacts: ArtifactRepository
    tasks: TaskRepository
    agent_runs: AgentRunRepository
    cost_ledger: CostLedgerRepository
    outbox: DomainEventOutbox

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self, context: ApplicationContext) -> ApplicationUnitOfWork: ...


class AuthorizationPort(Protocol):
    async def require(
        self,
        context: ApplicationContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None: ...


class IdempotencyClaimState(StrEnum):
    ACQUIRED = "acquired"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    state: IdempotencyClaimState
    result_ref: str | None = None


class IdempotencyPort(Protocol):
    async def claim(
        self,
        context: ApplicationContext,
        *,
        key: str,
        operation_type: str,
        request_hash: str,
    ) -> IdempotencyClaim: ...

    async def complete(
        self,
        context: ApplicationContext,
        *,
        key: str,
        result_ref: str | None,
    ) -> None: ...

    async def fail(
        self,
        context: ApplicationContext,
        *,
        key: str,
        error_code: str,
    ) -> None: ...


class Clock(Protocol):
    def now(self): ...


ResultLoader = Callable[[str], Awaitable[object]]
