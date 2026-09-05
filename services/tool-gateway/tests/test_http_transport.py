from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.contracts import (
    ToolCallStatus,
    ToolPermissionContext,
    ToolRequest,
    ToolResult,
    canonical_json_bytes,
)
from lumi_tool_gateway.http_transport import (
    INVOKE_PATH,
    InternalToolGatewayAuthError,
    decode_tool_request,
    decode_tool_result,
    encode_tool_request,
    encode_tool_result,
    sign_internal_request,
    verify_internal_request,
)


class ToolGatewayHttpTransportTests(unittest.TestCase):
    def _request(self) -> ToolRequest:
        organization_id = uuid4()
        return ToolRequest(
            tool_call_id=uuid4(),
            organization_id=organization_id,
            agent_run_id=uuid4(),
            task_id=uuid4(),
            actor_agent="design-agent",
            name="project.query",
            version="1.0.0",
            arguments={"query": "project.summary"},
            purpose="Summarize project state for the active design task.",
            permission_context=ToolPermissionContext(
                organization_id=organization_id,
                actor_id="agent-runtime:design-agent",
                granted_permissions=frozenset({"tool.project.query"}),
                agent_allow_patterns=("project.*",),
                parent_allow_patterns=("project.query",),
                organization_allow_patterns=("project.*",),
                organization_deny_patterns=("project.delete",),
            ),
            trace_id="trace-123",
        )

    def test_request_round_trip_preserves_tenant_and_permission_scope(self) -> None:
        original = self._request()
        decoded = decode_tool_request(encode_tool_request(original))
        self.assertEqual(decoded, original)
        self.assertEqual(decoded.organization_id, decoded.permission_context.organization_id)

    def test_result_round_trip_preserves_execution_metadata(self) -> None:
        original = ToolResult(
            tool_call_id=uuid4(),
            status=ToolCallStatus.SUCCEEDED,
            resolved_name="project.query",
            resolved_version="1.0.0",
            summary="ok",
            data={"items": [{"id": "a"}]},
            resource_refs=("project://a",),
            replayed=True,
            approval_id="approval-1",
        )
        self.assertEqual(decode_tool_result(encode_tool_result(original)), original)

    def test_hmac_binds_service_method_path_and_body(self) -> None:
        secret = "s" * 64
        body = canonical_json_bytes(encode_tool_request(self._request()))
        headers = sign_internal_request(
            secret=secret,
            service="agent-runtime",
            method="POST",
            path=INVOKE_PATH,
            body=body,
            timestamp=1_700_000_000,
        )
        caller = verify_internal_request(
            secret=secret,
            allowed_services=frozenset({"agent-runtime"}),
            method="POST",
            path=INVOKE_PATH,
            body=body,
            service=headers.service,
            timestamp=str(headers.timestamp),
            signature=headers.signature,
            now=1_700_000_010,
        )
        self.assertEqual(caller, "agent-runtime")

        with self.assertRaises(InternalToolGatewayAuthError):
            verify_internal_request(
                secret=secret,
                allowed_services=frozenset({"agent-runtime"}),
                method="POST",
                path=INVOKE_PATH,
                body=body + b" ",
                service=headers.service,
                timestamp=str(headers.timestamp),
                signature=headers.signature,
                now=1_700_000_010,
            )

    def test_hmac_rejects_expired_and_unapproved_callers(self) -> None:
        secret = "s" * 64
        body = b"{}"
        headers = sign_internal_request(
            secret=secret,
            service="agent-runtime",
            method="POST",
            path=INVOKE_PATH,
            body=body,
            timestamp=1_700_000_000,
        )
        with self.assertRaisesRegex(
            InternalToolGatewayAuthError,
            "TOOL_GATEWAY_AUTH_TIMESTAMP_EXPIRED",
        ):
            verify_internal_request(
                secret=secret,
                allowed_services=frozenset({"agent-runtime"}),
                method="POST",
                path=INVOKE_PATH,
                body=body,
                service=headers.service,
                timestamp=str(headers.timestamp),
                signature=headers.signature,
                now=1_700_000_500,
            )
        with self.assertRaisesRegex(
            InternalToolGatewayAuthError,
            "TOOL_GATEWAY_CALLER_FORBIDDEN",
        ):
            verify_internal_request(
                secret=secret,
                allowed_services=frozenset({"worker-media"}),
                method="POST",
                path=INVOKE_PATH,
                body=body,
                service=headers.service,
                timestamp=str(headers.timestamp),
                signature=headers.signature,
                now=1_700_000_000,
            )


if __name__ == "__main__":
    unittest.main()
