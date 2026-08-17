from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/memory_engine"


def require_text(path: Path, *needles: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [f"{path}: missing {needle}" for needle in needles if needle not in text]


def validate_ast(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    banned = {"subprocess", "requests", "httpx", "socket"}
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in banned:
                    failures.append(f"{path}: ambient dependency {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in banned:
                failures.append(f"{path}: ambient dependency {node.module}")
    return failures


def main() -> int:
    failures: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        failures.extend(validate_ast(path))

    failures.extend(
        require_text(
            PACKAGE / "context_source.py",
            "InstructionAuthority.NONE",
            "TrustLevel.UNTRUSTED_RETRIEVED",
            "ContextKind.MEMORY",
            "required_memory_scope=record.scope.permission_key",
        )
    )
    failures.extend(
        require_text(
            PACKAGE / "engine.py",
            "MEMORY_WRITE_DENIED",
            "MEMORY_READ_DENIED",
            "MemoryStatus.TOMBSTONE",
            "expected_parent_ref",
        )
    )
    failures.extend(
        require_text(
            PACKAGE / "contracts.py",
            "MEMORY_PRIVATE_REASONING_FORBIDDEN",
            "memory_content_hash",
            "memory://",
        )
    )
    failures.extend(
        require_text(
            PACKAGE / "store.py",
            "os.replace",
            "os.fsync",
            "MEMORY_STORE_PARENT_MISMATCH",
            "MEMORY_STORE_REVISION_GAP",
        )
    )

    if failures:
        print("NODE-35 Memory Engine validation FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("NODE-35 Memory Engine validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
