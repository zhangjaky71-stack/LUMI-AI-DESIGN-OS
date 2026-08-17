from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path("apps/agent-runtime/src/lumi_agent_runtime/context_engine")
FORBIDDEN_IMPORTS = {
    "anthropic",
    "asyncpg",
    "boto3",
    "docker",
    "google.generativeai",
    "httpx",
    "openai",
    "psycopg",
    "requests",
    "sqlalchemy",
    "subprocess",
}
REQUIRED_FILES = {
    "__init__.py",
    "budget.py",
    "builder.py",
    "bundle_source.py",
    "cache.py",
    "compression.py",
    "contracts.py",
    "errors.py",
    "integration.py",
    "profiles.py",
    "render.py",
    "retrieval.py",
    "safety.py",
    "source.py",
    "store.py",
}


def main() -> None:
    missing = sorted(REQUIRED_FILES - {path.name for path in ROOT.glob("*.py")})
    if missing:
        raise SystemExit(f"NODE34_MISSING_FILES:{','.join(missing)}")

    errors: list[str] = []
    for path in sorted(ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check_import(path, alias.name, errors)
            elif isinstance(node, ast.ImportFrom):
                _check_import(path, node.module or "", errors)
            elif isinstance(node, ast.Call):
                if _is_os_system(node.func):
                    errors.append(f"{path}: os.system is forbidden")
        if len(source.splitlines()) > 500:
            errors.append(f"{path}: file exceeds 500-line maintainability limit")

    integration = (ROOT / "integration.py").read_text(encoding="utf-8")
    if "runtime_context_ref" not in integration:
        errors.append("integration.py: runtime context provenance ref missing")
    if "bundle.task_context =" in integration:
        errors.append("integration.py: NODE-32 bundle mutation detected")

    if errors:
        raise SystemExit("\n".join(errors))
    print("NODE34_CONTEXT_ENGINE_CONTRACT_OK")


def _check_import(path: Path, name: str, errors: list[str]) -> None:
    root = name.split(".", 1)[0]
    if name in FORBIDDEN_IMPORTS or root in FORBIDDEN_IMPORTS:
        errors.append(f"{path}: forbidden ambient import {name}")


def _is_os_system(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "system"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )


if __name__ == "__main__":
    main()
