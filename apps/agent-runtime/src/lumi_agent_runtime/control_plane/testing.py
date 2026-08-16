from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .contracts import RunControlSnapshot, SafeRunEvent
from .errors import ResumeVersionConflict, RunConflict, RunNotFound


class MemoryRunControlStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunControlSnapshot] = {}

    async def load(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
    ) -> RunControlSnapshot | None:
        snapshot = self.runs.get(agent_run_id)
        if snapshot is None or snapshot.organization_id != organization_id:
            return None
        return snapshot

    async def create(self, snapshot: RunControlSnapshot) -> None:
        if snapshot.agent_run_id in self.runs:
            raise RunConflict("RUN_CONTROL_ALREADY_EXISTS")
        if any(
            existing.organization_id == snapshot.organization_id
            and existing.thread_id == snapshot.thread_id
            for existing in self.runs.values()
        ):
            raise RunConflict("THREAD_ALREADY_BOUND")
        self.runs[snapshot.agent_run_id] = snapshot

    async def compare_and_set(
        self,
        snapshot: RunControlSnapshot,
        *,
        expected_checkpoint_id: str | None,
        expected_resume_version: int,
    ) -> None:
        current = self.runs.get(snapshot.agent_run_id)
        if current is None or current.organization_id != snapshot.organization_id:
            raise RunNotFound(str(snapshot.agent_run_id))
        if current.checkpoint_id != expected_checkpoint_id:
            raise RunConflict("CHECKPOINT_CAS_MISMATCH")
        if current.resume_version != expected_resume_version:
            raise ResumeVersionConflict("RESUME_VERSION_CAS_MISMATCH")
        self.runs[snapshot.agent_run_id] = snapshot


class MemoryOperationGuard:
    def __init__(self) -> None:
        self.results: dict[tuple[UUID, str], tuple[str, RunControlSnapshot]] = {}
        self.executions = 0

    async def execute(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        operation_type: str,
        request_hash: str,
        invoke,
    ) -> RunControlSnapshot:
        del organization_id
        key = (operation_id, operation_type)
        existing = self.results.get(key)
        if existing is not None:
            old_hash, snapshot = existing
            if old_hash != request_hash:
                raise RunConflict("OPERATION_REPLAY_HASH_MISMATCH")
            return snapshot
        self.executions += 1
        snapshot = await invoke()
        self.results[key] = (request_hash, snapshot)
        return snapshot


class MemoryEventSink:
    def __init__(self) -> None:
        self.events: list[SafeRunEvent] = []

    async def publish(self, event: SafeRunEvent) -> None:
        self.events.append(event)


class AllowResumeAuthorizer:
    async def authorize(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        interrupt_id: str,
        resume_version: int,
        value: Any,
    ) -> Any:
        del organization_id, project_id, agent_run_id, interrupt_id, resume_version
        return value


class MemoryCancellationPort:
    def __init__(self) -> None:
        self.cancel_calls = 0
        self.release_calls = 0

    async def cancel_pending(self, state) -> None:
        del state
        self.cancel_calls += 1

    async def release_reservations(self, state) -> None:
        del state
        self.release_calls += 1


@dataclass(slots=True)
class ScriptedProjectPort:
    context_ref: str = "context://project-snapshot"

    async def load_project_snapshot(self, state):
        del state
        return {"context_ref": self.context_ref}


class ScriptedRecipePort:
    async def select_recipe(self, state):
        del state
        return {"version": "fixture@1.0.0"}


class ScriptedTaskGraphPort:
    def __init__(self, routes: list[str]) -> None:
        self.routes = list(routes)

    async def ensure_task_graph(self, state):
        del state
        return ["task-1"]

    async def next_route(self, state):
        del state
        return self.routes.pop(0) if self.routes else "done"


class ScriptedTaskPort:
    def __init__(self, delta: dict[str, Any] | None = None) -> None:
        self.delta = delta or {}
        self.calls = 0

    async def execute(self, state):
        del state
        self.calls += 1
        return dict(self.delta)

    async def execute_idempotent(self, state):
        return await self.execute(state)


class ScriptedExternalJobPort:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.collect_calls = 0
        self.job_id = "job-fixture-1"

    async def submit_idempotent(self, state):
        del state
        self.submit_calls += 1
        return self.job_id

    async def collect_completed(self, state):
        del state
        self.collect_calls += 1
        return {"artifact_refs": ["artifact://video-1"]}


class ScriptedQualityPort:
    def __init__(self, decisions: list[str] | None = None) -> None:
        self.decisions = list(decisions or ["finalize"])

    async def evaluate(self, state):
        del state
        return self.decisions.pop(0) if self.decisions else "finalize"
