from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from .native import HTTPTransportResponse


class PinnedStdlibHTTPTransport:
    """Connect to a prevalidated IP while preserving the original HTTP/TLS hostname."""

    async def fetch(
        self,
        *,
        url: str,
        resolved_ip: str,
        host_header: str,
        timeout_seconds: float,
        max_bytes: int,
        headers: dict[str, str],
    ) -> HTTPTransportResponse:
        return await asyncio.to_thread(
            self._fetch_sync,
            url=url,
            resolved_ip=resolved_ip,
            host_header=host_header,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            headers=headers,
        )

    def _fetch_sync(
        self,
        *,
        url: str,
        resolved_ip: str,
        host_header: str,
        timeout_seconds: float,
        max_bytes: int,
        headers: dict[str, str],
    ) -> HTTPTransportResponse:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").rstrip(".").lower()
        expected_host = host_header.rstrip(".").lower()
        if scheme not in {"http", "https"} or not hostname or hostname != expected_host:
            raise ValueError("TOOL_PINNED_TRANSPORT_TARGET_INVALID")
        try:
            pinned = str(ipaddress.ip_address(resolved_ip))
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("TOOL_PINNED_TRANSPORT_TARGET_INVALID") from exc
        if not 1 <= port <= 65535:
            raise ValueError("TOOL_PINNED_TRANSPORT_PORT_INVALID")
        if not 0.1 <= timeout_seconds <= 60.0:
            raise ValueError("TOOL_PINNED_TRANSPORT_TIMEOUT_INVALID")
        if not 1024 <= max_bytes <= 16 * 1024 * 1024:
            raise ValueError("TOOL_PINNED_TRANSPORT_RESPONSE_LIMIT_INVALID")

        request_headers = _validated_headers(headers)
        default_port = 443 if scheme == "https" else 80
        request_headers["Host"] = hostname if port == default_port else f"{hostname}:{port}"
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        connection: http.client.HTTPConnection
        if scheme == "https":
            connection = _PinnedHTTPSConnection(
                hostname,
                port,
                pinned_ip=pinned,
                timeout=timeout_seconds,
            )
        else:
            connection = _PinnedHTTPConnection(
                hostname,
                port,
                pinned_ip=pinned,
                timeout=timeout_seconds,
            )
        try:
            connection.request("GET", path, headers=request_headers)
            response = connection.getresponse()
            body = response.read(max_bytes + 1)
            response_headers = {key: value for key, value in response.getheaders()}
            return HTTPTransportResponse(
                status=int(response.status),
                headers=response_headers,
                body=body,
            )
        finally:
            connection.close()


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        pinned_ip: str,
        timeout: float,
    ) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        pinned_ip: str,
        timeout: float,
    ) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = raw_socket
            self._tunnel()
            raw_socket = self.sock
        self.sock = self._context.wrap_socket(
            raw_socket,
            server_hostname=self.host,
        )


def _validated_headers(headers: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        if not key or any(char in key for char in "\r\n:"):
            raise ValueError("TOOL_PINNED_TRANSPORT_HEADER_INVALID")
        if "\r" in value or "\n" in value:
            raise ValueError("TOOL_PINNED_TRANSPORT_HEADER_INVALID")
        if key.lower() in {"host", "authorization", "cookie", "proxy-authorization"}:
            continue
        result[key] = value
    return result
