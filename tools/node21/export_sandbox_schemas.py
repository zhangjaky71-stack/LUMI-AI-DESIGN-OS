from __future__ import annotations

import json
from pathlib import Path

from lumi_sandbox_runtime.models import (
    CollectedArtifact,
    ExecResult,
    SandboxAccessContext,
    SandboxAuditEvent,
    SandboxCommand,
    SandboxHandle,
    SandboxSpec,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports/nodes/NODE-21/generated-schemas"
SCHEMAS = {
    "sandbox-spec-v1": SandboxSpec,
    "sandbox-command-v1": SandboxCommand,
    "sandbox-exec-result-v1": ExecResult,
    "sandbox-handle-v1": SandboxHandle,
    "sandbox-audit-event-v1": SandboxAuditEvent,
    "sandbox-collected-artifact-v1": CollectedArtifact,
    "sandbox-access-context-v1": SandboxAccessContext,
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        path = OUTPUT / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path.relative_to(ROOT))
    print(f"NODE21_SANDBOX_SCHEMAS_EXPORTED: {len(SCHEMAS)}")


if __name__ == "__main__":
    main()
