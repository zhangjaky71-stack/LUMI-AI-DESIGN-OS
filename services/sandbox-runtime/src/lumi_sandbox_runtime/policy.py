from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import NetworkPolicy, SandboxCommand, SandboxSpec


class SandboxPolicyDenied(ValueError):
    code = "SANDBOX_POLICY_DENIED"


_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)

_DEFAULT_EXECUTABLES = frozenset(
    {
        "python",
        "python3",
        "node",
        "ffmpeg",
        "ffprobe",
        "magick",
        "convert",
        "identify",
        "zip",
        "unzip",
        "fc-list",
    }
)

_FORBIDDEN_EXECUTABLES = frozenset(
    {
        "bash",
        "sh",
        "dash",
        "zsh",
        "fish",
        "curl",
        "wget",
        "nc",
        "netcat",
        "ssh",
        "scp",
        "socat",
        "docker",
        "podman",
        "nsenter",
        "mount",
        "umount",
        "sudo",
        "su",
    }
)

_FORBIDDEN_ENV_MARKERS = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DATABASE_URL",
    "PGPASSWORD",
    "DOCKER_HOST",
)


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    allowed_executables: frozenset[str] = _DEFAULT_EXECUTABLES

    def validate(self, command: SandboxCommand) -> None:
        executable = command.argv[0].rsplit("/", 1)[-1]
        if executable in _FORBIDDEN_EXECUTABLES:
            raise SandboxPolicyDenied(f"executable is forbidden: {executable}")
        if executable not in self.allowed_executables:
            raise SandboxPolicyDenied(f"executable is not approved: {executable}")
        if not command.cwd.startswith("/workspace/"):
            raise SandboxPolicyDenied("cwd must remain inside /workspace")
        for key in command.env:
            normalized = key.upper()
            if any(normalized.startswith(marker) for marker in _FORBIDDEN_ENV_MARKERS):
                raise SandboxPolicyDenied(f"long-lived secret env is forbidden: {key}")


def address_is_blocked(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in _BLOCKED_NETWORKS)


def validate_allowlist_destination(destination: str) -> str:
    parsed = urlparse(destination if "://" in destination else f"https://{destination}")
    host = parsed.hostname
    if not host:
        raise SandboxPolicyDenied("allowlist destination requires a hostname")
    if host.lower() in {"localhost", "host.docker.internal", "metadata.google.internal"}:
        raise SandboxPolicyDenied(f"blocked internal hostname: {host}")
    if address_is_blocked(host):
        raise SandboxPolicyDenied(f"blocked internal address: {host}")
    if parsed.scheme not in {"http", "https"}:
        raise SandboxPolicyDenied("only HTTP(S) allowlist destinations are supported")
    return host.lower()


def validate_network_policy(spec: SandboxSpec, *, egress_enforcer_available: bool) -> None:
    if spec.network_policy is NetworkPolicy.NONE:
        return
    if not egress_enforcer_available:
        raise SandboxPolicyDenied(
            "network policy requires a real egress enforcement adapter; unrestricted bridge networking is forbidden"
        )
    if spec.network_policy is NetworkPolicy.ALLOWLIST:
        for destination in spec.network_allowlist:
            validate_allowlist_destination(destination)
