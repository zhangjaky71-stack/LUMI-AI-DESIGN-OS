from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.contracts import ToolPermissionContext, ToolRequest
from lumi_tool_gateway.errors import (
    ToolResponseTooLargeError,
    ToolSSRFBlockedError,
    ToolUnsupportedContentTypeError,
)
from lumi_tool_gateway.native import HTTPTransportResponse, SafeWebFetchAdapter
from lumi_tool_gateway.ssrf import SSRFPolicy


class StaticResolver:
    def __init__(self, values: dict[str, tuple[str, ...]]) -> None:
        self.values = values
        self.calls: list[str] = []

    def resolve(self, hostname: str) -> tuple[str, ...]:
        self.calls.append(hostname)
        return self.values[hostname]


class FakeTransport:
    def __init__(self, responses: list[HTTPTransportResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def fetch(self, **kwargs) -> HTTPTransportResponse:
        self.calls.append(dict(kwargs))
        return self.responses.pop(0)


def request(url: str) -> ToolRequest:
    definition = build_p0_registry().resolve("web.fetch", "1.0.0")
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="researcher",
        name=definition.name,
        version=definition.version,
        arguments={"url": url},
        purpose="retrieve public research source",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="user-1",
            granted_permissions=definition.permissions,
            agent_allow_patterns=(definition.name,),
        ),
    )


class SSRFPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_blocks_loopback_private_link_local_and_metadata_hosts(self) -> None:
        policy = SSRFPolicy()
        blocked = (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://localhost/",
            "http://metadata.google.internal/",
            "http://host.docker.internal/",
        )
        for url in blocked:
            with self.subTest(url=url), self.assertRaises(ToolSSRFBlockedError):
                policy.validate(url)

    def test_mixed_public_private_dns_answer_fails_closed(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8", "10.1.2.3")})
        policy = SSRFPolicy(resolver=resolver)
        with self.assertRaises(ToolSSRFBlockedError):
            policy.validate("https://public.example/path")

    def test_public_target_returns_pinned_validated_ip(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8", "1.1.1.1")})
        target = SSRFPolicy(resolver=resolver).validate("https://public.example/path")
        self.assertEqual(target.hostname, "public.example")
        self.assertIn(target.pinned_ip, {"1.1.1.1", "8.8.8.8"})
        self.assertEqual(target.port, 443)

    async def test_redirect_to_metadata_is_revalidated_before_second_fetch(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8",)})
        transport = FakeTransport(
            [
                HTTPTransportResponse(
                    status=302,
                    headers={"Location": "http://169.254.169.254/latest/meta-data/"},
                    body=b"",
                )
            ]
        )
        adapter = SafeWebFetchAdapter(
            transport,
            ssrf_policy=SSRFPolicy(resolver=resolver),
        )
        definition = build_p0_registry().resolve("web.fetch", "1.0.0")
        with self.assertRaises(ToolSSRFBlockedError):
            await adapter.invoke(definition, request("https://public.example/start"))
        self.assertEqual(len(transport.calls), 1)

    async def test_transport_receives_validated_pinned_ip_and_no_ambient_auth(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8",)})
        transport = FakeTransport(
            [
                HTTPTransportResponse(
                    status=200,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                    body=b"hello",
                )
            ]
        )
        adapter = SafeWebFetchAdapter(
            transport,
            ssrf_policy=SSRFPolicy(resolver=resolver),
        )
        definition = build_p0_registry().resolve("web.fetch", "1.0.0")
        result = await adapter.invoke(definition, request("https://public.example/a"))
        call = transport.calls[0]
        self.assertEqual(call["resolved_ip"], "8.8.8.8")
        self.assertEqual(call["host_header"], "public.example")
        headers = call["headers"]
        assert isinstance(headers, dict)
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Cookie", headers)
        self.assertEqual(result.data["text"], "hello")

    async def test_content_type_is_restricted(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8",)})
        transport = FakeTransport(
            [
                HTTPTransportResponse(
                    status=200,
                    headers={"Content-Type": "application/octet-stream"},
                    body=b"binary",
                )
            ]
        )
        adapter = SafeWebFetchAdapter(
            transport,
            ssrf_policy=SSRFPolicy(resolver=resolver),
        )
        definition = build_p0_registry().resolve("web.fetch", "1.0.0")
        with self.assertRaises(ToolUnsupportedContentTypeError):
            await adapter.invoke(definition, request("https://public.example/file"))

    async def test_response_body_limit_is_enforced(self) -> None:
        resolver = StaticResolver({"public.example": ("8.8.8.8",)})
        transport = FakeTransport(
            [
                HTTPTransportResponse(
                    status=200,
                    headers={"Content-Type": "text/plain"},
                    body=b"x" * 2048,
                )
            ]
        )
        adapter = SafeWebFetchAdapter(
            transport,
            ssrf_policy=SSRFPolicy(resolver=resolver),
            max_response_bytes=1024,
        )
        definition = build_p0_registry().resolve("web.fetch", "1.0.0")
        with self.assertRaises(ToolResponseTooLargeError):
            await adapter.invoke(definition, request("https://public.example/large"))


if __name__ == "__main__":
    unittest.main()
