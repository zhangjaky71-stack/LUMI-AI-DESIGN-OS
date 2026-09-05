from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.approval_control import HttpApprovalResolver
from lumi_tool_gateway.contracts import (
    ApprovalDecision,
    ToolDefinition,
    ToolIdempotency,
    ToolPermissionContext,
    ToolRequest,
    ToolRisk,
    ToolRuntime,
)
from lumi_tool_gateway.errors import ToolApprovalControlUnavailableError


def _definition() -> ToolDefinition:
    return ToolDefinition(
        name="publish.external",
        version="1.0.0",
        description="publish",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk=ToolRisk.WRITE_EXTERNAL,
        idempotency=ToolIdempotency.REQUIRED,
        permissions=frozenset({"tool.publish.external"}),
        runtime=ToolRuntime.NATIVE,
    )


def _request(*, approval_token: str | None = None) -> ToolRequest:
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="publisher",
        name="publish.external",
        version="1.0.0",
        arguments={"artifact_id": str(uuid4())},
        purpose="publish approved artifact",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="user-1",
            granted_permissions=frozenset({"tool.publish.external"}),
            agent_allow_patterns=("publish.external",),
        ),
        idempotency_key="publish-approval-0001",
        approval_token=approval_token,
    )


class HttpApprovalResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_required_and_forwards_existing_approval_token(self) -> None:
        resolver = HttpApprovalResolver(base_url="http://api.internal:8000", auth_secret="x" * 64)
        expected_approval = str(uuid4())
        seen = {}

        async def fake_post(payload):
            seen.update(payload)
            return {
                "decision": "REQUIRED",
                "approval_id": expected_approval,
                "reason_code": "TOOL_APPROVAL_REQUIRED",
            }

        resolver._post = fake_post  # type: ignore[method-assign]
        request = _request(approval_token="existing-approval-id")
        result = await resolver.resolve(_definition(), request)

        self.assertEqual(result.decision, ApprovalDecision.REQUIRED)
        self.assertEqual(result.approval_id, expected_approval)
        self.assertEqual(seen["approval_id"], "existing-approval-id")
        self.assertEqual(seen["tool_key"], "publish.external@1.0.0")

    async def test_maps_approved_and_denied(self) -> None:
        resolver = HttpApprovalResolver(base_url="http://api.internal:8000", auth_secret="x" * 64)
        approval_id = str(uuid4())

        async def approved(_payload):
            return {
                "decision": "APPROVED",
                "approval_id": approval_id,
                "reason_code": "TOOL_APPROVAL_APPROVED",
            }

        resolver._post = approved  # type: ignore[method-assign]
        allowed = await resolver.resolve(_definition(), _request(approval_token=approval_id))
        self.assertEqual(allowed.decision, ApprovalDecision.APPROVED)

        async def denied(_payload):
            return {
                "decision": "DENIED",
                "approval_id": approval_id,
                "reason_code": "TOOL_APPROVAL_SCOPE_MISMATCH",
            }

        resolver._post = denied  # type: ignore[method-assign]
        rejected = await resolver.resolve(_definition(), _request(approval_token=approval_id))
        self.assertEqual(rejected.decision, ApprovalDecision.DENIED)

    async def test_invalid_control_response_fails_closed(self) -> None:
        resolver = HttpApprovalResolver(base_url="http://api.internal:8000", auth_secret="x" * 64)

        async def invalid(_payload):
            return {"decision": "APPROVED", "approval_id": ""}

        resolver._post = invalid  # type: ignore[method-assign]
        with self.assertRaises(ToolApprovalControlUnavailableError):
            await resolver.resolve(_definition(), _request())


if __name__ == "__main__":
    unittest.main()
