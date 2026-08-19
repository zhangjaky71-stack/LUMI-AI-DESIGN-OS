from __future__ import annotations

import asyncio
import json
import os
import socket
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .contracts import (
    ToolAdapterOutput,
    ToolSideEffectContext,
    ToolSideEffectResponse,
    canonical_json_bytes,
)
from .errors import (
    ToolAmbiguousSideEffectError,
    ToolIdempotencyConflictError,
    ToolIdempotencyInProgressError,
    ToolPriorSideEffectFailedError,
    ToolSideEffectControlUnavailableError,
)
from .http_transport import sign_internal_request

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 15.0


class HttpSideEffectControlClient:
    """Private NODE-25 -> NODE-20 control-plane client.

    The API remains the only writer of idempotency lease/replay/ambiguity state.
    Tool Gateway never duplicates the idempotency SQL contract.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("SIDE_EFFECT_CONTROL_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("SIDE_EFFECT_CONTROL_URL_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("SIDE_EFFECT_CONTROL_AUTH_SECRET_INVALID")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("SIDE_EFFECT_CONTROL_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> HttpSideEffectControlClient:
        return cls(
            base_url=os.getenv("LUMI_SIDE_EFFECT_CONTROL_URL", ""),
            auth_secret=os.getenv("LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET", ""),
        )

    async def claim(
        self,
        context: ToolSideEffectContext,
        *,
        lease_owner: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/internal/v1/side-effects/claim",
            {
                "organization_id": str(context.organization_id),
                "operation_type": context.operation_type,
                "idempotency_key": context.idempotency_key,
                "request": context.request,
                "business_scope_id": str(context.business_scope_id),
                "lease_owner": lease_owner,
                "lease_seconds": 120,
            },
        )

    async def mark_attempt(self, operation_id: str, *, lease_owner: str) -> None:
        await self._post(
            f"/internal/v1/side-effects/{operation_id}/attempt",
            {"lease_owner": lease_owner},
        )

    async def succeed(
        self,
        operation_id: str,
        *,
        lease_owner: str,
        output: ToolAdapterOutput,
    ) -> None:
        await self._post(
            f"/internal/v1/side-effects/{operation_id}/succeed",
            {
                "lease_owner": lease_owner,
                "result_ref": output.side_effect_ref,
                "result_json": {"tool_adapter_output": _encode_output(output)},
                "response_status": 200,
            },
        )

    async def ambiguous(
        self,
        operation_id: str,
        *,
        lease_owner: str,
        reason: str,
    ) -> None:
        await self._post(
            f"/internal/v1/side-effects/{operation_id}/ambiguous",
            {"lease_owner": lease_owner, "reason": reason[:2000]},
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json_bytes(payload)
        auth = sign_internal_request(
            secret=self.auth_secret,
            service="tool-gateway",
            method="POST",
            path=path,
            body=body,
        )
        headers = {
            **auth.as_dict(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
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
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_RESPONSE_BYTES + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ToolSideEffectControlUnavailableError(
                "NODE-20 side-effect control plane is unavailable"
            ) from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ToolSideEffectControlUnavailableError(
                "NODE-20 side-effect control response exceeded limit"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolSideEffectControlUnavailableError(
                "NODE-20 side-effect control returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ToolSideEffectControlUnavailableError(
                "NODE-20 side-effect control response must be an object"
            )
        if not 200 <= status < 300:
            code = str(payload.get("code") or "SIDE_EFFECT_CONTROL_ERROR")
            message = str(payload.get("message") or "side-effect control request failed")
            if code == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST":
                raise ToolIdempotencyConflictError(message)
            if code in {"IDEMPOTENCY_OPERATION_IN_PROGRESS", "IDEMPOTENCY_LEASE_LOST"}:
                raise ToolIdempotencyInProgressError(message)
            if code in {"AMBIGUOUS_SIDE_EFFECT", "PROVIDER_ATTEMPT_OUTCOME_UNKNOWN"}:
                raise ToolAmbiguousSideEffectError(message)
            raise ToolSideEffectControlUnavailableError(f"{code}:{message}")
        return dict(payload)


class RemoteSideEffectGuard:
    """Durable Tool Gateway side-effect guard backed by the canonical NODE-20 ledger."""

    def __init__(self, client: HttpSideEffectControlClient) -> None:
        self.client = client

    async def execute(
        self,
        context: ToolSideEffectContext,
        invoke: Callable[[], Awaitable[ToolAdapterOutput]],
    ) -> ToolSideEffectResponse:
        lease_owner = _lease_owner()
        claim = await self.client.claim(context, lease_owner=lease_owner)
        decision = str(claim.get("decision") or "")
        operation_id = str(claim.get("operation_id") or "")
        if not operation_id:
            raise ToolSideEffectControlUnavailableError(
                "NODE-20 side-effect claim returned no operation id"
            )
        if decision == "replay":
            result_json = claim.get("result_json")
            if not isinstance(result_json, dict):
                raise ToolSideEffectControlUnavailableError(
                    "NODE-20 replay payload is invalid"
                )
            encoded = result_json.get("tool_adapter_output")
            if not isinstance(encoded, dict):
                raise ToolSideEffectControlUnavailableError(
                    "NODE-20 replay has no Tool Adapter output"
                )
            return ToolSideEffectResponse(
                output=_decode_output(encoded),
                replayed=True,
                operation_id=operation_id,
            )
        if decision == "wait":
            raise ToolIdempotencyInProgressError(
                "an equivalent tool side effect already owns the NODE-20 lease"
            )
        if decision == "final_failure":
            raise ToolPriorSideEffectFailedError(
                str(claim.get("error_code") or "prior tool side effect failed")
            )
        if decision in {"ambiguous", "reconcile"}:
            if decision == "reconcile":
                try:
                    await self.client.ambiguous(
                        operation_id,
                        lease_owner=lease_owner,
                        reason=(
                            "generic Tool Gateway side effect has no provider-native reconciliation "
                            "adapter; automatic re-execution is forbidden"
                        ),
                    )
                except Exception:
                    pass
            raise ToolAmbiguousSideEffectError(
                str(claim.get("ambiguity_reason") or "tool side-effect outcome is ambiguous")
            )
        if decision != "execute":
            raise ToolSideEffectControlUnavailableError(
                f"unexpected NODE-20 side-effect decision: {decision or 'missing'}"
            )

        await self.client.mark_attempt(operation_id, lease_owner=lease_owner)
        try:
            output = await invoke()
        except Exception as exc:
            try:
                await self.client.ambiguous(
                    operation_id,
                    lease_owner=lease_owner,
                    reason=(
                        "tool adapter failed after NODE-20 provider-attempt barrier; "
                        f"automatic re-execution is forbidden: {type(exc).__name__}"
                    ),
                )
            except Exception:
                # The durable attempt barrier is already set. If the ambiguity write also
                # fails, a later stale-lease claim in NODE-20 converts the row to ambiguous.
                pass
            raise ToolAmbiguousSideEffectError(
                "tool side effect failed after the durable external-attempt barrier"
            ) from exc

        try:
            await self.client.succeed(
                operation_id,
                lease_owner=lease_owner,
                output=output,
            )
        except Exception as exc:
            # The external effect completed but durable success did not. Never return success
            # or retry automatically; NODE-20's attempt barrier keeps the operation safe.
            raise ToolAmbiguousSideEffectError(
                "tool side effect completed but durable success commit failed"
            ) from exc
        return ToolSideEffectResponse(
            output=output,
            replayed=False,
            operation_id=operation_id,
        )


def _encode_output(output: ToolAdapterOutput) -> dict[str, Any]:
    return {
        "data": output.data,
        "summary": output.summary,
        "resource_refs": list(output.resource_refs),
        "side_effect_ref": output.side_effect_ref,
    }


def _decode_output(payload: dict[str, Any]) -> ToolAdapterOutput:
    refs = payload.get("resource_refs", [])
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        raise ToolSideEffectControlUnavailableError("NODE-20 replay resource refs are invalid")
    summary = payload.get("summary", "")
    if not isinstance(summary, str):
        raise ToolSideEffectControlUnavailableError("NODE-20 replay summary is invalid")
    side_effect_ref = payload.get("side_effect_ref")
    if side_effect_ref is not None and not isinstance(side_effect_ref, str):
        raise ToolSideEffectControlUnavailableError("NODE-20 replay side-effect ref is invalid")
    return ToolAdapterOutput(
        data=payload.get("data", {}),
        summary=summary,
        resource_refs=tuple(refs),
        side_effect_ref=side_effect_ref,
    )


def _lease_owner() -> str:
    hostname = socket.gethostname().replace(" ", "-")[:64] or "unknown"
    return f"tool-gateway:{hostname}:{uuid4()}"
