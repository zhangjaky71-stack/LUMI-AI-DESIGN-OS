from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from .errors import ToolSSRFBlockedError

_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "host.docker.internal",
        "gateway.docker.internal",
        "metadata.google.internal",
        "metadata",
    }
)


class HostResolver(Protocol):
    def resolve(self, hostname: str) -> tuple[str, ...]: ...


class SystemHostResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        try:
            rows = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise ToolSSRFBlockedError("TOOL_DNS_RESOLUTION_FAILED") from exc
        addresses = sorted({row[4][0] for row in rows})
        if not addresses:
            raise ToolSSRFBlockedError("TOOL_DNS_EMPTY")
        return tuple(addresses)


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    resolved_ips: tuple[str, ...]

    @property
    def pinned_ip(self) -> str:
        return self.resolved_ips[0]


class SSRFPolicy:
    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        allowed_ports: frozenset[int] = frozenset({80, 443}),
    ) -> None:
        self.resolver = resolver or SystemHostResolver()
        self.allowed_ports = allowed_ports
        if not self.allowed_ports:
            raise ValueError("TOOL_SSRF_ALLOWED_PORTS_REQUIRED")
        if any(port < 1 or port > 65535 for port in self.allowed_ports):
            raise ValueError("TOOL_SSRF_ALLOWED_PORT_INVALID")

    def validate(self, url: str) -> ValidatedTarget:
        if not url or len(url) > 4096:
            raise ToolSSRFBlockedError("TOOL_URL_INVALID")
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ToolSSRFBlockedError("TOOL_URL_INVALID") from exc
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ToolSSRFBlockedError("TOOL_URL_SCHEME_BLOCKED")
        if parsed.username is not None or parsed.password is not None:
            raise ToolSSRFBlockedError("TOOL_URL_USERINFO_BLOCKED")
        if parsed.fragment:
            raise ToolSSRFBlockedError("TOOL_URL_FRAGMENT_BLOCKED")
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if not hostname:
            raise ToolSSRFBlockedError("TOOL_URL_HOST_REQUIRED")
        if hostname in _BLOCKED_HOSTS or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
            raise ToolSSRFBlockedError("TOOL_HOST_BLOCKED")
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise ToolSSRFBlockedError("TOOL_URL_PORT_INVALID") from exc
        if port not in self.allowed_ports:
            raise ToolSSRFBlockedError("TOOL_URL_PORT_BLOCKED")

        literal = _parse_ip(hostname)
        addresses = (
            (str(literal),)
            if literal is not None
            else self.resolver.resolve(hostname)
        )
        normalized: list[str] = []
        for address in addresses:
            ip = _parse_ip(address)
            if ip is None or not _is_public(ip):
                raise ToolSSRFBlockedError(f"TOOL_IP_BLOCKED:{address}")
            normalized.append(str(ip))
        if not normalized:
            raise ToolSSRFBlockedError("TOOL_DNS_EMPTY")
        return ValidatedTarget(
            url=url,
            scheme=scheme,
            hostname=hostname,
            port=port,
            resolved_ips=tuple(sorted(set(normalized))),
        )


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_global
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_private
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )
