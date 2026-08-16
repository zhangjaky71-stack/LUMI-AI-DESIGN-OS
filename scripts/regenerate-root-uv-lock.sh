#!/usr/bin/env bash
set -euo pipefail

REQUIRED_PYTHON="3.12"
REQUIRED_UV="0.11.28"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

python_version="$(python --version 2>&1 | awk '{print $2}')"
uv_version="$(uv --version 2>&1 | awk '{print $2}')"

case "$python_version" in
  3.12.*) ;;
  *)
    echo "ERROR: Python ${REQUIRED_PYTHON}.x is required; found ${python_version}" >&2
    exit 2
    ;;
esac

if [[ "$uv_version" != "$REQUIRED_UV" ]]; then
  echo "ERROR: uv ${REQUIRED_UV} is required; found ${uv_version}" >&2
  exit 2
fi

if [[ -n "$(git status --porcelain -- pyproject.toml '*/pyproject.toml' '*/*/pyproject.toml' uv.lock)" ]]; then
  echo "ERROR: pyproject.toml/uv.lock inputs must be clean before regeneration." >&2
  git status --short -- pyproject.toml '*/pyproject.toml' '*/*/pyproject.toml' uv.lock >&2
  exit 3
fi

before_sha="$(sha256sum uv.lock | awk '{print $1}')"

# Let uv resolve the current workspace manifest. Never hand-edit uv.lock.
uv lock
uv lock --check
uv sync --all-packages --frozen

python - <<'PY'
from __future__ import annotations

from pathlib import Path
import tomllib

root = Path.cwd()
root_manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
members = root_manifest["tool"]["uv"]["workspace"]["members"]
lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
locked_names = {package["name"] for package in lock.get("package", [])}

missing: list[str] = []
for member in members:
    manifest_path = root / member / "pyproject.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    name = manifest["project"]["name"]
    if name not in locked_names:
        missing.append(f"{member} ({name})")

if missing:
    raise SystemExit("workspace members missing from uv.lock: " + ", ".join(missing))

print(f"LOCK_WORKSPACE_MEMBERS_OK count={len(members)}")
PY

after_sha="$(sha256sum uv.lock | awk '{print $1}')"
if [[ "$before_sha" == "$after_sha" ]]; then
  echo "ERROR: uv.lock did not change; stale-lock blocker was not actually repaired." >&2
  exit 4
fi

if [[ -n "$(git diff --name-only -- . ':!uv.lock')" ]]; then
  echo "ERROR: lock regeneration changed files other than uv.lock." >&2
  git diff --name-only -- . ':!uv.lock' >&2
  exit 5
fi

printf 'ROOT_UV_LOCK_REGENERATED\npython=%s\nuv=%s\nbefore=%s\nafter=%s\n' \
  "$python_version" "$uv_version" "$before_sha" "$after_sha"

git diff --stat -- uv.lock
echo "Review the uv.lock diff, then commit it normally. Do not edit the lock by hand."
