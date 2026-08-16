from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from .contracts import LumiRunState, RunControlSnapshot, SafeRunEvent


class RunControlStore(Protocol):
    async def load(self, agent_run_id: UUID) -> RunControlSnapshot | None: ...

    async def create(self, snapshot: RunControlSnapshot) -> None: ...

    async def compare_and_set(
        self,
        snapshot: RunControlSnapshot,
        *,
        expected_checkpoint_id: str | None,
        expected_resume_version: int,
    ) -> None: ...


class OperationGuard(Protocol):
    async def execute(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        operation_type: str,
        request_hash: str,
        invoke: Callable[[], Awaitable[RunControlSnapshot]],
    ) -> RunControlSnapshot: ...


class ResumeAuthorizer(Protocol):
    async def authorize(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        interrupt_id: str,
        resume_version: int,
        value: Any,
    ) -> Any: ...


class EventSink(Protocol):
    async def publish(self, event: SafeRunEvent) -> None: ...


class ProjectSnapshotPort(Protocol):
    async def load_project_snapshot(self, state: LumiRunState) -> dict[str, Any]: ...


class RecipePort(Protocol):
    async def select_recipe(self, state: LumiRunState) -> dict[str, Any]: ...


class TaskGraphPort(Protocol):
    async def ensure_task_graph(self, state: LumiRunState) -> list[str]: ...

    async def next_route(self, state: LumiRunState) -> str: ...


class DeterministicTaskPort(Protocol):
    async def execute(self, state: LumiRunState) -> dict[str, Any]: ...


class AgenticTaskPort(Protocol):
    async def execute(self, state: LumiRunState) -> dict[str, Any]: ...


class SideEffectTaskPort(Protocol):
    async def execute_idempotent(self, state: LumiRunState) -> dict[str, Any]: ...


class ExternalJobPort(Protocol):
    async def submit_idempotent(self, state: LumiRunState) -> str: ...

    async def collect_completed(self, state: LumiRunState) -> dict[str, Any]: ...


class QualityGatePort(Protocol):
    async def evaluate(self, state: LumiRunState) -> str: ...


class CancellationPort(Protocol):
    async def cancel_pending(self, state: LumiRunState) -> None: ...

    async def release_reservations(self, state: LumiRunState) -> None: ...


@dataclass(slots=True)
class ControlServices:
    project: ProjectSnapshotPort
    recipes: RecipePort
    tasks: TaskGraphPort
    deterministic: DeterministicTaskPort
    agentic: AgenticTaskPort
    side_effects: SideEffectTaskPort
    external_jobs: ExternalJobPort
    quality: QualityGatePort
    cancellation: CancellationPort
    events: EventSink
