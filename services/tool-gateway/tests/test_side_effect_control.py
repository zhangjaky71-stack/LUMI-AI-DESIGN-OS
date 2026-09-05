from __future__ import annotations

import unittest
from typing import Any
from uuid import uuid4

from lumi_tool_gateway.contracts import (
    ToolAdapterOutput,
    ToolSideEffectContext,
)
from lumi_tool_gateway.errors import (
    ToolAmbiguousSideEffectError,
    ToolIdempotencyInProgressError,
    ToolPriorSideEffectFailedError,
)
from lumi_tool_gateway.side_effect_control import RemoteSideEffectGuard


class _FakeSideEffectControlClient:
    def __init__(self, claim: dict[str, Any]) -> None:
        self.claim_payload = dict(claim)
        self.calls: list[tuple[str, str | None]] = []
        self.fail_succeed = False

    async def claim(
        self,
        context: ToolSideEffectContext,
        *,
        lease_owner: str,
    ) -> dict[str, Any]:
        del context
        self.calls.append(("claim", lease_owner))
        return dict(self.claim_payload)

    async def mark_attempt(self, operation_id: str, *, lease_owner: str) -> None:
        self.calls.append((f"attempt:{operation_id}", lease_owner))

    async def succeed(
        self,
        operation_id: str,
        *,
        lease_owner: str,
        output: ToolAdapterOutput,
    ) -> None:
        del output
        self.calls.append((f"succeed:{operation_id}", lease_owner))
        if self.fail_succeed:
            raise RuntimeError("durable success unavailable")

    async def ambiguous(
        self,
        operation_id: str,
        *,
        lease_owner: str,
        reason: str,
    ) -> None:
        del reason
        self.calls.append((f"ambiguous:{operation_id}", lease_owner))


def _context() -> ToolSideEffectContext:
    return ToolSideEffectContext(
        organization_id=uuid4(),
        operation_type="tool:sandbox.execute:1.0.0",
        idempotency_key="idem-sandbox-1",
        request={
            "tool": "sandbox.execute@1.0.0",
            "arguments": {"command": ["python", "-V"]},
        },
        business_scope_id=uuid4(),
    )


async def _invoke_once(counter: list[int]) -> ToolAdapterOutput:
    counter.append(1)
    return ToolAdapterOutput(
        data={"exit_code": 0, "stdout": "Python 3.12"},
        summary="sandbox command completed",
        resource_refs=("sandbox://result/1",),
        side_effect_ref="sandbox-operation-1",
    )


class RemoteSideEffectGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_sets_attempt_barrier_before_callback_and_commits_success(self) -> None:
        operation_id = str(uuid4())
        client = _FakeSideEffectControlClient(
            {"decision": "execute", "operation_id": operation_id, "status": "in_progress"}
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        response = await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [1])
        self.assertFalse(response.replayed)
        self.assertEqual(response.operation_id, operation_id)
        self.assertEqual(response.output.side_effect_ref, "sandbox-operation-1")
        names = [name for name, _ in client.calls]
        self.assertEqual(names[0], "claim")
        self.assertEqual(names[1], f"attempt:{operation_id}")
        self.assertEqual(names[2], f"succeed:{operation_id}")
        lease_owners = [lease for _, lease in client.calls if lease is not None]
        self.assertTrue(lease_owners)
        self.assertEqual(len(set(lease_owners)), 1)

    async def test_replay_returns_durable_output_without_invoking_adapter(self) -> None:
        operation_id = str(uuid4())
        client = _FakeSideEffectControlClient(
            {
                "decision": "replay",
                "operation_id": operation_id,
                "status": "succeeded",
                "result_json": {
                    "tool_adapter_output": {
                        "data": {"exit_code": 0},
                        "summary": "already completed",
                        "resource_refs": ["sandbox://result/replayed"],
                        "side_effect_ref": "sandbox-operation-replayed",
                    }
                },
            }
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        response = await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [])
        self.assertTrue(response.replayed)
        self.assertEqual(response.operation_id, operation_id)
        self.assertEqual(response.output.summary, "already completed")
        self.assertEqual(client.calls[0][0], "claim")
        self.assertEqual(len(client.calls), 1)

    async def test_wait_never_invokes_adapter(self) -> None:
        client = _FakeSideEffectControlClient(
            {"decision": "wait", "operation_id": str(uuid4()), "status": "in_progress"}
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        with self.assertRaises(ToolIdempotencyInProgressError):
            await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [])
        self.assertEqual(len(client.calls), 1)

    async def test_final_failure_never_invokes_adapter(self) -> None:
        client = _FakeSideEffectControlClient(
            {
                "decision": "final_failure",
                "operation_id": str(uuid4()),
                "status": "failed_final",
                "error_code": "PROVIDER_REJECTED",
            }
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        with self.assertRaises(ToolPriorSideEffectFailedError):
            await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [])

    async def test_adapter_failure_after_attempt_barrier_becomes_ambiguous(self) -> None:
        operation_id = str(uuid4())
        client = _FakeSideEffectControlClient(
            {"decision": "execute", "operation_id": operation_id, "status": "in_progress"}
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]

        async def fail_after_attempt() -> ToolAdapterOutput:
            raise RuntimeError("remote provider timeout after send")

        with self.assertRaises(ToolAmbiguousSideEffectError):
            await guard.execute(_context(), fail_after_attempt)

        names = [name for name, _ in client.calls]
        self.assertEqual(
            names[:3],
            [
                "claim",
                f"attempt:{operation_id}",
                f"ambiguous:{operation_id}",
            ],
        )
        self.assertNotIn(f"succeed:{operation_id}", names)

    async def test_success_commit_failure_never_returns_success_or_reexecutes(self) -> None:
        operation_id = str(uuid4())
        client = _FakeSideEffectControlClient(
            {"decision": "execute", "operation_id": operation_id, "status": "in_progress"}
        )
        client.fail_succeed = True
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        with self.assertRaises(ToolAmbiguousSideEffectError):
            await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [1])
        names = [name for name, _ in client.calls]
        self.assertEqual(names.count(f"attempt:{operation_id}"), 1)
        self.assertEqual(names.count(f"succeed:{operation_id}"), 1)

    async def test_ambiguous_claim_never_invokes_adapter(self) -> None:
        client = _FakeSideEffectControlClient(
            {
                "decision": "ambiguous",
                "operation_id": str(uuid4()),
                "status": "ambiguous",
                "ambiguity_reason": "provider outcome unknown",
            }
        )
        guard = RemoteSideEffectGuard(client)  # type: ignore[arg-type]
        counter: list[int] = []

        with self.assertRaises(ToolAmbiguousSideEffectError):
            await guard.execute(_context(), lambda: _invoke_once(counter))

        self.assertEqual(counter, [])


if __name__ == "__main__":
    unittest.main()
