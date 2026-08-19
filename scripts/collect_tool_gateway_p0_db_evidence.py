#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from lumi_api.persistence.session import create_engine

_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_DEFAULT_PROBE = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-db-evidence.json"
_RIGHTS_FIELDS = (
    "scope",
    "source",
    "attribution_required",
    "policy_json",
    "source_type",
    "owner_assertion",
    "license_type",
    "commercial_use",
    "redistribution",
    "training_use",
    "source_reference",
    "review_status",
)


class DBEvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DBEvidenceError(f"unable to read probe JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise DBEvidenceError("probe JSON must be an object")
    return payload


def _uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise DBEvidenceError(f"{label} must be a UUID string")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise DBEvidenceError(f"{label} must be a UUID") from exc


def _table_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise DBEvidenceError(f"unsafe database table identifier: {value}")
    return value


def _probe_scope(probe: dict[str, Any]) -> dict[str, str]:
    scope = probe.get("scope")
    if not isinstance(scope, dict):
        raise DBEvidenceError("probe scope is missing")
    return {
        "organization_id": _uuid(scope.get("organization_id"), "scope.organization_id"),
        "agent_run_id": _uuid(scope.get("agent_run_id"), "scope.agent_run_id"),
        "task_id": _uuid(scope.get("task_id"), "scope.task_id"),
        "source_asset_id": _uuid(scope.get("source_asset_id"), "scope.source_asset_id"),
        "artifact_id": _uuid(scope.get("artifact_id"), "scope.artifact_id"),
    }


def _tool_calls(probe: dict[str, Any]) -> dict[str, str]:
    calls = probe.get("calls")
    if not isinstance(calls, dict) or len(calls) != 8:
        raise DBEvidenceError("probe calls must contain the 8 first P0 calls")
    result: dict[str, str] = {}
    for tool, value in calls.items():
        if not isinstance(tool, str) or not isinstance(value, dict):
            raise DBEvidenceError("probe call entry is invalid")
        request = value.get("request")
        if not isinstance(request, dict):
            raise DBEvidenceError(f"probe call request is missing: {tool}")
        result[tool] = _uuid(request.get("tool_call_id"), f"calls.{tool}.tool_call_id")
    return result


def _replay_call_id(probe: dict[str, Any]) -> str:
    replay = probe.get("idempotent_replay")
    if not isinstance(replay, dict):
        raise DBEvidenceError("probe idempotent_replay is missing")
    return _uuid(replay.get("replay_tool_call_id"), "idempotent_replay.replay_tool_call_id")


def _offload_call_id(probe: dict[str, Any]) -> str:
    offload = probe.get("result_offload")
    if not isinstance(offload, dict):
        raise DBEvidenceError("probe result_offload is missing")
    return _uuid(offload.get("tool_call_id"), "result_offload.tool_call_id")


async def _schema_columns(connection: Any) -> dict[str, set[str]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
        )
    ).all()
    result: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        if isinstance(table_name, str) and isinstance(column_name, str):
            result.setdefault(table_name, set()).add(column_name)
    return result


def _discover_table(
    schema: dict[str, set[str]],
    *,
    required: set[str],
    preferred_names: tuple[str, ...],
    label: str,
) -> tuple[str, set[str]]:
    candidates = [
        (name, columns)
        for name, columns in schema.items()
        if required.issubset(columns)
    ]
    for preferred in preferred_names:
        for name, columns in candidates:
            if name == preferred:
                return _table_identifier(name), columns
    if len(candidates) != 1:
        names = sorted(name for name, _ in candidates)
        raise DBEvidenceError(
            f"unable to discover unique {label} table from required columns; candidates={names}"
        )
    name, columns = candidates[0]
    return _table_identifier(name), columns


def _uuid_in_clause(prefix: str, values: list[str]) -> tuple[str, dict[str, str]]:
    params: dict[str, str] = {}
    markers: list[str] = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        params[key] = value
        markers.append(f"CAST(:{key} AS uuid)")
    return ", ".join(markers), params


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    return str(value)


async def _audit_evidence(
    connection: Any,
    *,
    table: str,
    columns: set[str],
    organization_id: str,
    call_ids: dict[str, str],
    replay_call_id: str,
    offload_call_id: str,
) -> dict[str, Any]:
    ids = [*call_ids.values(), replay_call_id, offload_call_id]
    if len(set(ids)) != 10:
        raise DBEvidenceError("P0 probe must expose 10 distinct Tool Gateway call IDs")
    markers, params = _uuid_in_clause("audit_call", ids)
    params["organization_id"] = organization_id
    selected = ["id", "tool_call_id", "organization_id", "created_at"]
    for optional in (
        "tool_name",
        "tool_key",
        "resolved_tool",
        "status",
        "event_type",
        "request_json",
        "response_json",
        "metadata_json",
        "details_json",
    ):
        if optional in columns and optional not in selected:
            selected.append(optional)
    projection = ", ".join(selected)
    rows = (
        await connection.execute(
            text(
                f"SELECT {projection} FROM {table} "
                f"WHERE tool_call_id IN ({markers}) ORDER BY created_at, id"
            ),
            params,
        )
    ).mappings().all()
    seen = {
        str(row["tool_call_id"])
        for row in rows
        if row.get("tool_call_id") is not None
    }
    missing = [tool for tool, call_id in call_ids.items() if call_id not in seen]
    if replay_call_id not in seen:
        missing.append("asset.write-derived:replay")
    if offload_call_id not in seen:
        missing.append("sandbox.execute:offload")

    cross_count = int(
        (
            await connection.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE tool_call_id IN ({markers}) "
                    "AND organization_id <> CAST(:organization_id AS uuid)"
                ),
                params,
            )
        ).scalar_one()
    )
    sensitive_values = [
        value
        for value in (
            os.getenv("LUMI_TOOL_GATEWAY_AUTH_SECRET"),
            os.getenv("DATABASE_URL"),
            os.getenv("LUMI_DATABASE_URL"),
        )
        if isinstance(value, str) and len(value) >= 8
    ]
    serialized_rows = json.dumps(
        [{key: _json_safe(value) for key, value in row.items()} for row in rows],
        sort_keys=True,
        default=str,
    )
    event_ids = {
        str(row["tool_call_id"]): str(row.get("id") or "")
        for row in rows
        if row.get("tool_call_id") is not None
    }
    return {
        "table": table,
        "expected_call_count": len(ids),
        "persisted_call_count": len(rows),
        "missing_tool_calls": missing,
        "cross_tenant_rows": cross_count,
        "secret_material_present": any(value in serialized_rows for value in sensitive_values),
        "event_ids_by_tool_call_id": event_ids,
    }


async def _idempotency_evidence(
    connection: Any,
    *,
    table: str,
    columns: set[str],
    organization_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    projection_names = [
        name
        for name in (
            "id",
            "operation_id",
            "operation_type",
            "idempotency_key",
            "status",
            "attempt_count",
            "side_effect_attempted",
            "result_json",
            "error_json",
            "created_at",
        )
        if name in columns
    ]
    projection = ", ".join(projection_names)
    row = (
        await connection.execute(
            text(
                f"SELECT {projection} FROM {table} "
                "WHERE organization_id = CAST(:organization_id AS uuid) "
                "AND idempotency_key = :idempotency_key "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"organization_id": organization_id, "idempotency_key": idempotency_key},
        )
    ).mappings().first()
    if row is None:
        raise DBEvidenceError("canonical idempotency operation for derived write was not found")
    operation_id = row.get("operation_id") or row.get("id")
    return {
        "table": table,
        "operation_id": str(operation_id or ""),
        "operation_type": str(row.get("operation_type") or ""),
        "status": str(row.get("status") or ""),
        "attempt_count": row.get("attempt_count"),
        "side_effect_attempted": row.get("side_effect_attempted"),
        "idempotency_key_hash": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
    }


async def _derived_assets(
    connection: Any,
    *,
    organization_id: str,
    task_project_id: str,
    first_tool_call_id: str,
    replay_tool_call_id: str,
) -> dict[str, Any]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, metadata_json
                FROM assets
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND project_id = CAST(:project_id AS uuid)
                  AND source = 'derived'
                  AND deleted_at IS NULL
                  AND metadata_json ->> 'tool_call_id' IN (:first_call, :replay_call)
                ORDER BY created_at, id
                """
            ),
            {
                "organization_id": organization_id,
                "project_id": task_project_id,
                "first_call": first_tool_call_id,
                "replay_call": replay_tool_call_id,
            },
        )
    ).mappings().all()
    first_rows = [
        row
        for row in rows
        if isinstance(row.get("metadata_json"), dict)
        and row["metadata_json"].get("tool_call_id") == first_tool_call_id
    ]
    if len(first_rows) != 1:
        raise DBEvidenceError(
            f"expected exactly one first-call derived Asset, found {len(first_rows)}"
        )
    derived_id = str(first_rows[0]["id"])
    return {
        "derived_asset_id": derived_id,
        "derived_asset_ref": f"asset://{derived_id}",
        "matching_asset_ids": [str(row["id"]) for row in rows],
        "adapter_invocation_count": len(first_rows),
        "duplicate_derived_asset_count": max(0, len(rows) - 1),
    }


async def _task_project_id(connection: Any, *, task_id: str, organization_id: str) -> str:
    value = (
        await connection.execute(
            text(
                "SELECT project_id FROM tasks "
                "WHERE id = CAST(:task_id AS uuid) "
                "AND organization_id = CAST(:organization_id AS uuid)"
            ),
            {"task_id": task_id, "organization_id": organization_id},
        )
    ).scalar_one_or_none()
    if value is None:
        raise DBEvidenceError("probe Task was not found in canonical PostgreSQL")
    return str(value)


async def _rights_evidence(
    connection: Any,
    *,
    organization_id: str,
    source_asset_id: str,
    derived_asset_id: str,
) -> dict[str, Any]:
    fields = ", ".join(_RIGHTS_FIELDS)
    rows = (
        await connection.execute(
            text(
                f"SELECT asset_id, {fields} FROM asset_rights "
                "WHERE organization_id = CAST(:organization_id AS uuid) "
                "AND asset_id IN (CAST(:source_asset_id AS uuid), CAST(:derived_asset_id AS uuid))"
            ),
            {
                "organization_id": organization_id,
                "source_asset_id": source_asset_id,
                "derived_asset_id": derived_asset_id,
            },
        )
    ).mappings().all()
    by_asset = {str(row["asset_id"]): row for row in rows}
    source = by_asset.get(source_asset_id)
    derived = by_asset.get(derived_asset_id)
    if source is None or derived is None:
        raise DBEvidenceError("source or derived AssetRights row is missing")
    mismatched = [field for field in _RIGHTS_FIELDS if source.get(field) != derived.get(field)]
    return {
        "source_asset_id": source_asset_id,
        "derived_asset_id": derived_asset_id,
        "rights_inherited": not mismatched,
        "mismatched_fields": mismatched,
    }


async def collect(probe: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
    scope = _probe_scope(probe)
    call_ids = _tool_calls(probe)
    replay_call_id = _replay_call_id(probe)
    offload_call_id = _offload_call_id(probe)
    first_write_call_id = call_ids["asset.write-derived"]

    engine = create_engine()
    try:
        async with engine.connect() as connection:
            schema = await _schema_columns(connection)
            audit_table, audit_columns = _discover_table(
                schema,
                required={"id", "created_at", "organization_id", "tool_call_id"},
                preferred_names=("tool_audit_events", "tool_audits", "audit_events"),
                label="Tool audit",
            )
            idempotency_table, idempotency_columns = _discover_table(
                schema,
                required={"id", "created_at", "organization_id", "idempotency_key"},
                preferred_names=("idempotency_operations", "idempotency_operation"),
                label="idempotency operation",
            )
            task_project_id = await _task_project_id(
                connection,
                task_id=scope["task_id"],
                organization_id=scope["organization_id"],
            )
            audit = await _audit_evidence(
                connection,
                table=audit_table,
                columns=audit_columns,
                organization_id=scope["organization_id"],
                call_ids=call_ids,
                replay_call_id=replay_call_id,
                offload_call_id=offload_call_id,
            )
            idempotency = await _idempotency_evidence(
                connection,
                table=idempotency_table,
                columns=idempotency_columns,
                organization_id=scope["organization_id"],
                idempotency_key=idempotency_key,
            )
            derived = await _derived_assets(
                connection,
                organization_id=scope["organization_id"],
                task_project_id=task_project_id,
                first_tool_call_id=first_write_call_id,
                replay_tool_call_id=replay_call_id,
            )
            rights = await _rights_evidence(
                connection,
                organization_id=scope["organization_id"],
                source_asset_id=scope["source_asset_id"],
                derived_asset_id=derived["derived_asset_id"],
            )
    finally:
        await engine.dispose()

    return {
        "schema_version": 1,
        "scope": {**scope, "project_id": task_project_id},
        "tool_call_ids": call_ids,
        "replay_tool_call_id": replay_call_id,
        "offload_tool_call_id": offload_call_id,
        "audit": audit,
        "idempotency": idempotency,
        "derived_asset": derived,
        "rights": rights,
    }


def main() -> int:
    probe_path = Path(os.getenv("LUMI_PROBE_INPUT", _DEFAULT_PROBE))
    output_path = Path(os.getenv("LUMI_DB_EVIDENCE_OUTPUT", _DEFAULT_OUTPUT))
    idempotency_key = os.getenv("LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY", "")
    if not idempotency_key or len(idempotency_key) > 256 or "\x00" in idempotency_key:
        raise SystemExit("LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY is required")
    try:
        payload = asyncio.run(collect(_load(probe_path), idempotency_key=idempotency_key))
    except DBEvidenceError as exc:
        raise SystemExit(f"Tool Gateway PostgreSQL evidence failed: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
