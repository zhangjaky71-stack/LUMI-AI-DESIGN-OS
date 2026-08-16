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
        '"final-accessibility-preflight.spec.ts"',
        "not accepted as",
    )
    require(
        "apps/web/e2e/final-accessibility-preflight.spec.ts",
        "unnamedInteractiveControls",
        "imagesMissingAlternative",
        'page.locator("main")',
        'name: "跳到主要内容"',
        'name: "命令面板"',
        'name: "用量与账单"',
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
        "A11Y-01",
        "Safari is no longer a deferrable P1 item",
        "exact browser version",
        "Manual keyboard and screen-reader checks are required",
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
