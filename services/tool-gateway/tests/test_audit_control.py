from __future__ import annotations

import json
import unittest
from uuid import uuid4

from lumi_tool_gateway.audit import ToolAuditRecord
from lumi_tool_gateway.audit_control import HttpAuditSink
from lumi_tool_gateway.errors import ToolAuditUnavailableError


class HttpAuditSinkTests(unittest.IsolatedAsyncioTestCase):
    def _record(self) -> ToolAuditRecord:
        return ToolAuditRecord(
            tool_call_id=str(uuid4()),
            organization_id=str(uuid4()),
            actor_id="agent:design",
            actor_agent="design-agent",
            resolved_tool="sandbox.execute@1.0.0",
            risk="write_internal",
            purpose="render deterministic artifact",
            status="succeeded",
            trace_id="trace-audit-1",
            arguments={"api_key": "[REDACTED]", "command": ["python", "render.py"]},
            side_effect_operation_id=str(uuid4()),
        )

    async def test_retry_reuses_same_event_identity_and_payload(self) -> None:
        sink = HttpAuditSink(
            base_url="http://api.staging.lumi.internal:8000",
            auth_secret="a" * 64,
        )
        record = self._record()
        calls: list[bytes] = []

        def fake_post(body: bytes, headers: dict[str, str]) -> None:
            del headers
            calls.append(body)
            if len(calls) == 1:
                raise ToolAuditUnavailableError("transient network failure")

        sink._post_sync = fake_post  # type: ignore[method-assign]
        await sink.record(record)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        payload = json.loads(calls[0].decode("utf-8"))
        self.assertEqual(payload["event_id"], record.event_id)
        self.assertEqual(payload["tool_call_id"], record.tool_call_id)
        self.assertEqual(payload["arguments"]["api_key"], "[REDACTED]")

    async def test_two_delivery_failures_fail_closed(self) -> None:
        sink = HttpAuditSink(
            base_url="http://api.staging.lumi.internal:8000",
            auth_secret="a" * 64,
        )
        calls = 0

        def fail_post(body: bytes, headers: dict[str, str]) -> None:
            nonlocal calls
            del body, headers
            calls += 1
            raise ToolAuditUnavailableError("audit unavailable")

        sink._post_sync = fail_post  # type: ignore[method-assign]
        with self.assertRaises(ToolAuditUnavailableError):
            await sink.record(self._record())

        self.assertEqual(calls, 2)

    async def test_event_id_is_stable_for_record_lifetime(self) -> None:
        record = self._record()
        self.assertEqual(record.event_id, record.event_id)
        self.assertEqual(len(record.event_id), 36)


if __name__ == "__main__":
    unittest.main()
