from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from lumi_tool_gateway.http_transport import sign_internal_request

from .contracts import (
    GraphInterrupt,
    GraphRunEvent,
    GraphRunSnapshot,
    GraphRunStatus,
    InterruptKind,
)
from .resume_policy import ApprovalDecisionRecord

_BASE_PATH = "/internal/v1/agent-control"
_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class AgentControlUnavailableError(RuntimeError):
    pass


class AgentControlRejectedError(RuntimeError):
    pass


class HttpAgentControlClient:
    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("AGENT_CONTROL_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("AGENT_CONTROL_URL_INVALID")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("AGENT_CONTROL_TIMEOUT_INVALID")
        if not 1024 <= max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError("AGENT_CONTROL_RESPONSE_LIMIT_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("AGENT_CONTROL_AUTH_SECRET_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_env(cls) -> HttpAgentControlClient:
        return cls(
            base_url=os.getenv("LUMI_AGENT_CONTROL_URL", ""),
            auth_secret=os.getenv("LUMI_AGENT_CONTROL_AUTH_SECRET", ""),
        )

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = _json_bytes(payload)
        headers = sign_internal_request(
            secret=self.auth_secret,
            service="agent-runtime",
            method="POST",
            path=path,
            body=body,
        ).as_dict()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        return await asyncio.to_thread(self._post_sync, path, body, headers)

    def _post_sync(
        self,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(self.max_response_bytes + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AgentControlUnavailableError("private Agent control request failed") from exc
        if len(raw) > self.max_response_bytes:
            raise AgentControlUnavailableError("private Agent control response exceeded limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AgentControlUnavailableError("private Agent control returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AgentControlUnavailableError("private Agent control response must be an object")
        if not 200 <= status < 300:
            code = str(payload.get("code") or "AGENT_CONTROL_HTTP_ERROR")[:128]
            message = str(payload.get("message") or "private Agent control request failed")[:2000]
            if status >= 500:
                raise AgentControlUnavailableError(f"{code}: {message}")
            raise AgentControlRejectedError(f"{code}: {message}")
        return dict(payload)


class RemoteControlPlaneOperationGuard:
    def __init__(self, client: HttpAgentControlClient) -> None:
        self.client = client

    async def execute(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        operation_type: str,
        request_hash: str,
        invoke: Callable[[], Awaitable[GraphRunSnapshot]],
    ) -> GraphRunSnapshot:
        lease_owner = f"agent-runtime:{uuid4()}"
        claim = await self.client.post(
            f"{_BASE_PATH}/operations/claim",
            {
                "organization_id": str(organization_id),
                "operation_id": str(operation_id),
                "operation_type": operation_type,
                "request_hash": request_hash,
                "lease_owner": lease_owner,
            },
        )
        decision = _required_string(claim, "decision")
        if decision == "replay":
            result_json = _required_dict(claim, "result_json")
            if result_json.get("schema_version") != 1:
                raise AgentControlUnavailableError("agent control replay schema is unsupported")
            return _snapshot_from_payload(_required_dict(result_json, "snapshot"))
        if decision != "execute":
            code = str(claim.get("error_code") or decision).upper()
            raise AgentControlRejectedError(f"control operation cannot execute: {code}")

        ledger_operation_id = UUID(_required_string(claim, "ledger_operation_id"))
        active_lease_owner = _required_string(claim, "lease_owner")
        try:
            snapshot = await invoke()
        except Exception:
            try:
                await self.client.post(
                    f"{_BASE_PATH}/operations/fail-final",
                    {
                        "ledger_operation_id": str(ledger_operation_id),
                        "lease_owner": active_lease_owner,
                        "error_code": "LANGGRAPH_CONTROL_EXECUTION_FAILED",
                    },
                )
            except Exception as commit_exc:
                raise AgentControlUnavailableError(
                    "graph command failed and its terminal idempotency state could not be committed"
                ) from commit_exc
            raise

        try:
            await self.client.post(
                f"{_BASE_PATH}/operations/succeed",
                {
                    "ledger_operation_id": str(ledger_operation_id),
                    "lease_owner": active_lease_owner,
                    "snapshot": _snapshot_payload(snapshot),
                },
            )
        except Exception as exc:
            try:
                await self.client.post(
                    f"{_BASE_PATH}/operations/ambiguous",
                    {
                        "ledger_operation_id": str(ledger_operation_id),
                        "lease_owner": active_lease_owner,
                        "reason": (
                            "graph command returned a durable snapshot, but the canonical "
                            "idempotency success commit was not confirmed"
                        ),
                    },
                )
            except Exception:
                pass
            raise AgentControlUnavailableError(
                "graph command completed but canonical idempotency success was not confirmed"
            ) from exc
        return snapshot


class RemoteApprovalDecisionReader:
    def __init__(self, client: HttpAgentControlClient) -> None:
        self.client = client

    async def get_approval(self, approval_id: UUID) -> ApprovalDecisionRecord:
        payload = await self.client.post(
            f"{_BASE_PATH}/approvals/read",
            {"approval_id": str(approval_id)},
        )
        return ApprovalDecisionRecord(
            approval_id=UUID(_required_string(payload, "approval_id")),
            organization_id=UUID(_required_string(payload, "organization_id")),
            project_id=UUID(_required_string(payload, "project_id")),
            agent_run_id=UUID(_required_string(payload, "agent_run_id")),
            status=_required_string(payload, "status"),
            decision_payload=_required_dict(payload, "decision_payload"),
        )


class RemoteGraphEventSink:
    def __init__(self, client: HttpAgentControlClient) -> None:
        self.client = client

    async def publish(self, event: GraphRunEvent) -> None:
        await self.client.post(
            f"{_BASE_PATH}/events/publish",
            {
                "event_type": event.event_type,
                "organization_id": str(event.organization_id),
                "project_id": str(event.project_id),
                "agent_run_id": str(event.agent_run_id),
                "thread_id": event.thread_id,
                "graph_key": event.graph_key,
                "graph_version": event.graph_version,
                "checkpoint_id": event.checkpoint_id,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": event.payload,
                "trace_id": event.trace_id,
            },
        )


def _snapshot_payload(snapshot: GraphRunSnapshot) -> dict[str, Any]:
    return {
        "organization_id": str(snapshot.organization_id),
        "project_id": str(snapshot.project_id),
        "agent_run_id": str(snapshot.agent_run_id),
        "task_id": str(snapshot.task_id) if snapshot.task_id else None,
        "thread_id": snapshot.thread_id,
        "graph_key": snapshot.graph_key,
        "graph_version": snapshot.graph_version,
        "agent_config_version": snapshot.agent_config_version,
        "status": snapshot.status.value,
        "checkpoint_id": snapshot.checkpoint_id,
        "checkpoint_namespace": snapshot.checkpoint_namespace,
        "state_values": snapshot.state_values,
        "next_nodes": list(snapshot.next_nodes),
        "interrupts": [
            {
                "interrupt_id": item.interrupt_id,
                "kind": item.kind.value,
                "namespace": list(item.namespace),
                "node_name": item.node_name,
                "payload": item.payload,
                "resumable": item.resumable,
                "created_at": item.created_at.isoformat(),
            }
            for item in snapshot.interrupts
        ],
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
        "error_code": snapshot.error_code,
    }


def _snapshot_from_payload(payload: dict[str, Any]) -> GraphRunSnapshot:
    interrupts_raw = payload.get("interrupts", [])
    if not isinstance(interrupts_raw, list):
        raise AgentControlUnavailableError("agent control replay interrupts are invalid")
    return GraphRunSnapshot(
        organization_id=UUID(_required_string(payload, "organization_id")),
        project_id=UUID(_required_string(payload, "project_id")),
        agent_run_id=UUID(_required_string(payload, "agent_run_id")),
        task_id=_optional_uuid(payload.get("task_id")),
        thread_id=_required_string(payload, "thread_id"),
        graph_key=_required_string(payload, "graph_key"),
        graph_version=_required_string(payload, "graph_version"),
        agent_config_version=_required_string(payload, "agent_config_version"),
        status=GraphRunStatus(_required_string(payload, "status")),
        checkpoint_id=_optional_string(payload.get("checkpoint_id")),
        checkpoint_namespace=_required_string_allow_empty(payload, "checkpoint_namespace"),
        state_values=_required_dict(payload, "state_values"),
        next_nodes=tuple(_required_string_list(payload, "next_nodes")),
        interrupts=tuple(_interrupt_from_payload(item) for item in interrupts_raw),
        created_at=_required_datetime(payload, "created_at"),
        updated_at=_required_datetime(payload, "updated_at"),
        error_code=_optional_string(payload.get("error_code")),
    )


def _interrupt_from_payload(value: Any) -> GraphInterrupt:
    if not isinstance(value, dict):
        raise AgentControlUnavailableError("agent control replay interrupt is invalid")
    return GraphInterrupt(
        interrupt_id=_required_string(value, "interrupt_id"),
        kind=InterruptKind(_required_string(value, "kind")),
        namespace=tuple(_required_string_list(value, "namespace")),
        node_name=_optional_string(value.get("node_name")),
        payload=_required_dict(value, "payload"),
        resumable=bool(value.get("resumable", False)),
        created_at=_required_datetime(value, "created_at"),
    )


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AgentControlUnavailableError(f"agent control field is invalid: {key}")
    return value


def _required_string_allow_empty(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise AgentControlUnavailableError(f"agent control field is invalid: {key}")
    return value


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise AgentControlUnavailableError(f"agent control object is invalid: {key}")
    return dict(value)


def _required_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AgentControlUnavailableError(f"agent control list is invalid: {key}")
    return list(value)


def _required_datetime(payload: dict[str, Any], key: str) -> datetime:
    raw = _required_string(payload, key)
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentControlUnavailableError(f"agent control datetime is invalid: {key}") from exc
    if value.tzinfo is None:
        raise AgentControlUnavailableError(f"agent control datetime is naive: {key}")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AgentControlUnavailableError("agent control optional string is invalid")
    return value


def _optional_uuid(value: Any) -> UUID | None:
    raw = _optional_string(value)
    return UUID(raw) if raw else None
