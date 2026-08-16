from __future__ import annotations

import inspect
from importlib.metadata import version

from deepagents.backends.protocol import (
    GlobResult,
    GrepResult,
    ReadResult,
    SandboxBackendProtocol,
)

from lumi_sandbox_runtime.deepagents_adapter import DeepAgentsSandboxAdapter

EXPECTED_VERSION = "0.6.12"


def parameters(target) -> tuple[str, ...]:
    return tuple(inspect.signature(target).parameters)


def main() -> None:
    installed = version("deepagents")
    if installed != EXPECTED_VERSION:
        raise SystemExit(
            f"Deep Agents lock drifted: expected {EXPECTED_VERSION}, got {installed}; "
            "review SandboxBackendProtocol before updating NODE-21 adapter"
        )
    if not issubclass(DeepAgentsSandboxAdapter, SandboxBackendProtocol):
        raise SystemExit("LUMI adapter no longer satisfies SandboxBackendProtocol")

    read_fields = set(parameters(ReadResult))
    grep_fields = set(parameters(GrepResult))
    glob_fields = set(parameters(GlobResult))
    if read_fields != {"error", "file_data"}:
        raise SystemExit(f"unexpected locked ReadResult shape: {sorted(read_fields)}")
    if grep_fields != {"error", "matches"}:
        raise SystemExit(f"unexpected locked GrepResult shape: {sorted(grep_fields)}")
    if glob_fields != {"error", "matches"}:
        raise SystemExit(f"unexpected locked GlobResult shape: {sorted(glob_fields)}")

    protocol_grep = parameters(SandboxBackendProtocol.grep)
    adapter_grep = parameters(DeepAgentsSandboxAdapter.grep)
    if protocol_grep != adapter_grep:
        raise SystemExit(
            f"grep signature mismatch: protocol={protocol_grep}, adapter={adapter_grep}"
        )
    protocol_read = parameters(SandboxBackendProtocol.read)
    adapter_read = parameters(DeepAgentsSandboxAdapter.read)
    if protocol_read != adapter_read:
        raise SystemExit(
            f"read signature mismatch: protocol={protocol_read}, adapter={adapter_read}"
        )
    protocol_execute = parameters(SandboxBackendProtocol.execute)
    adapter_execute = parameters(DeepAgentsSandboxAdapter.execute)
    if protocol_execute != adapter_execute:
        raise SystemExit(
            "execute signature mismatch: "
            f"protocol={protocol_execute}, adapter={adapter_execute}"
        )

    print(
        "NODE21_DEEPAGENTS_LOCK_VALID: "
        f"deepagents={installed}; read={sorted(read_fields)}; "
        f"grep={sorted(grep_fields)}; glob={sorted(glob_fields)}"
    )


if __name__ == "__main__":
    main()
