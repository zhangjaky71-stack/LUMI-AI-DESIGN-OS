from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/security-release-gate.yml",
    ".github/workflows/ai-regression-release-gate.yml",
    ".github/workflows/staging-acceptance-gate.yml",
    ".github/workflows/final-acceptance-gate.yml",
)


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: canonical dependency contract missing {missing}")


def main() -> None:
    for path in CANONICAL_WORKFLOWS:
        text = (ROOT / path).read_text(encoding="utf-8")
        if "0.11.28" not in text:
            raise SystemExit(f"{path}: canonical uv 0.11.28 pin missing")
        if "uv sync --all-packages --frozen" not in text:
            raise SystemExit(f"{path}: canonical all-package frozen sync missing")
        if "astral-sh/setup-uv@v6" in text:
            raise SystemExit(f"{path}: obsolete unpinned setup-uv@v6 remains")
        if "python-version: \"3.12\"" not in text and "PYTHON_VERSION: \"3.12\"" not in text:
            raise SystemExit(f"{path}: canonical Python 3.12 pin missing")

    require(
        "scripts/regenerate-root-uv-lock.sh",
        'REQUIRED_PYTHON="3.12"',
        'REQUIRED_UV="0.11.28"',
        "uv lock",
        "uv lock --check",
        "uv sync --all-packages --frozen",
        "workspace members missing from uv.lock",
        "uv.lock did not change",
        "lock regeneration changed files other than uv.lock",
        "Do not edit the lock by hand",
    )

    print("FINAL_UPSTREAM_LOCK_STATIC_CONTRACT_PASS")


if __name__ == "__main__":
    main()
