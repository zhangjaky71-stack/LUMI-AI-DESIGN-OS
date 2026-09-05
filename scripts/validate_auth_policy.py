from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/auth/src/lumi_auth"
FORBIDDEN = (
    "fastapi","sqlalchemy","alembic","argon2","langchain","langgraph","openai","anthropic",
    "boto3","httpx","requests","celery","pika",
)


def main() -> None:
    files = sorted(SOURCE.glob("*.py"))
    assert files, "lumi_auth source missing"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(FORBIDDEN):
                    raise AssertionError(f"auth policy leaked implementation dependency {name}: {path.relative_to(ROOT)}")
                if name.startswith("lumi_") and not name.startswith("lumi_auth"):
                    raise AssertionError(f"auth policy must be standalone: {name}")
    print(f"Auth policy boundary OK: {len(files)} modules, stdlib-only policy core")


if __name__ == "__main__":
    main()
