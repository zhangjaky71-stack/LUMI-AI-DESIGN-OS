from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: missing final browser preflight contract(s): {missing}")


def main() -> None:
    require(
        "playwright.final-acceptance.config.ts",
        'name: "chrome-stable"',
        'channel: "chrome"',
        'name: "edge-stable"',
        'channel: "msedge"',
        'name: "firefox-engine"',
        'name: "webkit-safari-engine-preflight"',
        '"app-shell.spec.ts"',
        '"projects.spec.ts"',
        '"ai-workspace.spec.ts"',
        '"canvas-engine.spec.ts"',
        '"layers-inspector.spec.ts"',
        '"versions-ui.spec.ts"',
        '"export-ui.spec.ts"',
        '"billing.spec.ts"',
        "not accepted as",
    )
    require(
        ".github/workflows/final-browser-preflight.yml",
        "pnpm install --frozen-lockfile",
        "playwright install-deps chromium firefox webkit",
        "playwright install firefox webkit chrome msedge",
        "browser-inventory.txt",
        "google-chrome --version",
        "microsoft-edge --version",
        "playwright install --list",
        "playwright.final-acceptance.config.ts",
        "MUST NOT be used as evidence that real macOS Safari passed BROWSER-02",
    )
    require(
        "docs/acceptance/NODE-73-UAT-SIGNOFF-MATRIX.md",
        "BROWSER-01",
        "BROWSER-02",
        "Safari is no longer a deferrable P1 item",
        "exact browser version",
    )
    require(
        "final/acceptance/manifest-v1.json",
        '"id":"BROWSER-01"',
        '"id":"BROWSER-02"',
        '"id":"A11Y-01"',
        '"priority":"P0"',
    )
    print("FINAL_BROWSER_PREFLIGHT_STATIC_CONTRACT_PASS")


if __name__ == "__main__":
    main()
