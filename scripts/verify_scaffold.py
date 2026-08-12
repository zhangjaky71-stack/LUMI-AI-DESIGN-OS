from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ".node-version",
    ".python-version",
    "package.json",
    "pnpm-workspace.yaml",
    "turbo.json",
    "pyproject.toml",
    ".env.example",
    "Makefile",
    "apps/web/src/app/page.tsx",
    "apps/web/src/app/health/page.tsx",
    "apps/api/src/lumi_api/main.py",
    "apps/agent-runtime/src/lumi_agent_runtime/smoke.py",
    "apps/worker-media/src/lumi_worker_media/app.py",
]

missing = [path for path in REQUIRED if not (ROOT / path).exists()]
if missing:
    raise SystemExit(f"Missing scaffold paths: {missing}")

for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    if path.name == ".env.example":
        continue
    if path.name == ".env" or path.name.startswith(".env."):
        raise SystemExit(f"Secret-like env file must not be committed: {path}")

print(f"scaffold-ok required={len(REQUIRED)}")
