from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from .contracts import MemoryKind, MemoryRecord, MemoryScope, MemoryScopeKind, MemoryStatus
from .errors import MemoryConflictError


class MemoryStore(Protocol):
    async def get_head(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        scope_key: str,
        memory_key: str,
    ) -> MemoryRecord | None: ...

    async def get_by_ref(self, memory_ref: str) -> MemoryRecord | None: ...

    async def get_by_idempotency(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> MemoryRecord | None: ...

    async def append(
        self,
        record: MemoryRecord,
        *,
        expected_parent_ref: str | None,
    ) -> MemoryRecord: ...

    async def list_heads(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> tuple[MemoryRecord, ...]: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._heads: dict[tuple[str, str, str, str], str] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _head_key(record: MemoryRecord) -> tuple[str, str, str, str]:
        return (
            str(record.organization_id),
            str(record.project_id) if record.project_id else "org",
            record.scope.permission_key,
            record.memory_key,
        )

    async def get_head(self, *, organization_id, project_id, scope_key, memory_key):
        key = (
            str(organization_id),
            str(project_id) if project_id else "org",
            scope_key,
            memory_key,
        )
        ref = self._heads.get(key)
        return self._records.get(ref) if ref else None

    async def get_by_ref(self, memory_ref: str) -> MemoryRecord | None:
        return self._records.get(memory_ref)

    async def get_by_idempotency(self, *, organization_id, idempotency_key):
        if not idempotency_key:
            return None
        ref = self._idempotency.get((str(organization_id), idempotency_key))
        return self._records.get(ref) if ref else None

    async def append(self, record: MemoryRecord, *, expected_parent_ref: str | None):
        async with self._lock:
            key = self._head_key(record)
            current_ref = self._heads.get(key)
            if current_ref != expected_parent_ref:
                raise MemoryConflictError("MEMORY_REVISION_CONFLICT")
            if record.memory_ref in self._records:
                return self._records[record.memory_ref]
            if record.idempotency_key:
                idem_key = (str(record.organization_id), record.idempotency_key)
                existing_ref = self._idempotency.get(idem_key)
                if existing_ref and existing_ref != record.memory_ref:
                    raise MemoryConflictError("MEMORY_IDEMPOTENCY_CONFLICT")
                self._idempotency[idem_key] = record.memory_ref
            self._records[record.memory_ref] = record
            self._heads[key] = record.memory_ref
            return record

    async def list_heads(self, *, organization_id, project_id):
        output: list[MemoryRecord] = []
        for key, ref in self._heads.items():
            if key[0] != str(organization_id):
                continue
            if key[1] not in {"org", str(project_id)}:
                continue
            output.append(self._records[ref])
        return tuple(output)


class GitWorkspaceMemoryStore(InMemoryMemoryStore):
    """Canonical JSON persistence without owning Git/network credentials."""

    def __init__(self, root: str | Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self) -> None:
        records: list[MemoryRecord] = []
        for path in sorted(self.root.glob("organizations/**/r*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = deserialize_record(data)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise MemoryConflictError(f"MEMORY_STORE_CORRUPT:{path}") from exc
            records.append(record)

        records.sort(
            key=lambda record: (
                str(record.organization_id),
                str(record.project_id) if record.project_id else "org",
                record.scope.permission_key,
                record.memory_key,
                record.revision,
            )
        )
        for record in records:
            key = self._head_key(record)
            current_ref = self._heads.get(key)
            if current_ref is not None:
                current = self._records[current_ref]
                if record.revision != current.revision + 1:
                    raise MemoryConflictError("MEMORY_STORE_REVISION_GAP")
                if record.parent_ref != current.memory_ref:
                    raise MemoryConflictError("MEMORY_STORE_PARENT_MISMATCH")
            elif record.revision != 1 or record.parent_ref is not None:
                raise MemoryConflictError("MEMORY_STORE_ROOT_INVALID")
            if record.memory_ref in self._records:
                raise MemoryConflictError("MEMORY_STORE_DUPLICATE_REF")
            if record.idempotency_key:
                idem_key = (str(record.organization_id), record.idempotency_key)
                existing_ref = self._idempotency.get(idem_key)
                if existing_ref and existing_ref != record.memory_ref:
                    raise MemoryConflictError("MEMORY_STORE_IDEMPOTENCY_CORRUPT")
                self._idempotency[idem_key] = record.memory_ref
            self._records[record.memory_ref] = record
            self._heads[key] = record.memory_ref

    async def append(self, record: MemoryRecord, *, expected_parent_ref: str | None):
        result = await super().append(record, expected_parent_ref=expected_parent_ref)
        path = self._path_for(result)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _serialize(result)
        fd, temp_name = tempfile.mkstemp(prefix=".memory-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return result

    def _path_for(self, record: MemoryRecord) -> Path:
        project = str(record.project_id) if record.project_id else "org"
        scope = record.scope.permission_key.replace(":", "__")
        return (
            self.root
            / "organizations"
            / str(record.organization_id)
            / project
            / scope
            / record.memory_key
            / f"r{record.revision}.json"
        )


def _serialize(record: MemoryRecord) -> dict[str, object]:
    data = asdict(record)
    data["organization_id"] = str(record.organization_id)
    data["project_id"] = str(record.project_id) if record.project_id else None
    data["scope"] = {"kind": record.scope.kind.value, "subject_id": record.scope.subject_id}
    data["kind"] = record.kind.value
    data["status"] = record.status.value
    data["agent_run_id"] = str(record.agent_run_id) if record.agent_run_id else None
    data["task_id"] = str(record.task_id) if record.task_id else None
    data["created_at"] = record.created_at.isoformat()
    data["expires_at"] = record.expires_at.isoformat() if record.expires_at else None
    return data


def deserialize_record(data: dict[str, object]) -> MemoryRecord:
    scope = data["scope"]
    assert isinstance(scope, dict)
    return MemoryRecord(
        organization_id=UUID(str(data["organization_id"])),
        project_id=UUID(str(data["project_id"])) if data.get("project_id") else None,
        scope=MemoryScope(MemoryScopeKind(str(scope["kind"])), scope.get("subject_id")),
        memory_key=str(data["memory_key"]),
        kind=MemoryKind(str(data["kind"])),
        status=MemoryStatus(str(data["status"])),
        revision=int(data["revision"]),
        content=str(data["content"]),
        confidence=float(data["confidence"]),
        importance=float(data["importance"]),
        source_refs=tuple(data.get("source_refs", [])),
        metadata=dict(data.get("metadata", {})),
        parent_ref=str(data["parent_ref"]) if data.get("parent_ref") else None,
        content_hash=str(data["content_hash"]),
        actor_id=str(data["actor_id"]),
        agent_run_id=UUID(str(data["agent_run_id"])) if data.get("agent_run_id") else None,
        task_id=UUID(str(data["task_id"])) if data.get("task_id") else None,
        created_at=datetime.fromisoformat(str(data["created_at"])),
        expires_at=(
            datetime.fromisoformat(str(data["expires_at"]))
            if data.get("expires_at")
            else None
        ),
        idempotency_key=str(data.get("idempotency_key", "")),
    )
