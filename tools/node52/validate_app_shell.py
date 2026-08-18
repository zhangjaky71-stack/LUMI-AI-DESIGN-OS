from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps/web"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"missing NODE-52 invariants: {missing}")


def forbid(text: str, *needles: str) -> None:
    found = [needle for needle in needles if needle in text]
    if found:
        raise AssertionError(f"forbidden NODE-52 patterns found: {found}")


def main() -> None:
    package = read("apps/web/package.json")
    require(package, '"next"', '"react"', '"typescript"', '"typecheck"', '"build"')

    config = read("apps/web/next.config.ts")
    require(
        config,
        'source: "/api/:path*"',
        "LUMI_API_ORIGIN",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "X-Frame-Options",
        "Permissions-Policy",
    )

    env = read("apps/web/src/lib/config/env.ts")
    require(
        env,
        "requireApiPath",
        'candidate.startsWith("/api/")',
        "LUMI_SESSION_PATH",
        "LUMI_SIGN_IN_PATH",
        "LUMI_SIGN_OUT_PATH",
    )

    browser_client = read("apps/web/src/lib/api/client.ts")
    require(
        browser_client,
        "requireApiPath(path)",
        'credentials: "include"',
        '"x-request-id"',
        "apiErrorFromResponse",
    )

    server_client = read("apps/web/src/lib/api/server.ts")
    require(
        server_client,
        "await cookies()",
        "getWebRuntimeConfig()",
        'cache: "no-store"',
        'redirect: "manual"',
        'headers.set("cookie"',
    )
    forbid(server_client.lower(), "authorization: bearer", "localstorage", "sessionstorage")

    session = read("apps/web/src/lib/auth/session.ts")
    session_types = read("apps/web/src/lib/auth/types.ts")
    require(
        session,
        "getAppSession",
        "requireAppSession",
        "error.status === 401",
        'redirect("/sign-in")',
    )
    require(
        session_types,
        "SessionOrganization",
        "SessionWorkspace",
        "parseAppSession",
        "SESSION_PERMISSIONS_INVALID",
    )

    shell_layout = read("apps/web/src/app/(shell)/layout.tsx")
    root_layout = read("apps/web/src/app/layout.tsx")
    nav = read("apps/web/src/components/shell/app-nav.tsx")
    require(shell_layout, "await requireAppSession()", "<AppShell")
    require(root_layout, 'className="skip-link"', 'href="#main-content"')
    require(nav, 'aria-label="Primary navigation"', 'aria-current={active ? "page"')

    sign_in = read("apps/web/src/app/(auth)/sign-in/page.tsx")
    require(sign_in, "await getAppSession()", "signInPath", "Continue to sign in")

    boundaries = "\n".join(
        [
            read("apps/web/src/app/error.tsx"),
            read("apps/web/src/app/loading.tsx"),
            read("apps/web/src/app/not-found.tsx"),
        ]
    )
    require(boundaries, "reset", 'aria-busy="true"', "Return home")

    css = read("apps/web/src/app/globals.css")
    require(
        css,
        ":focus-visible",
        ".skip-link",
        "prefers-reduced-motion",
        "@media (max-width: 720px)",
    )

    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (WEB / "src").rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css"}
    ).lower()
    forbid(source_text, "localstorage", "sessionstorage", "document.cookie")

    for route in (
        "apps/web/src/app/(shell)/page.tsx",
        "apps/web/src/app/(shell)/projects/page.tsx",
        "apps/web/src/app/(shell)/workspace/page.tsx",
        "apps/web/src/app/(shell)/settings/page.tsx",
    ):
        if not (ROOT / route).exists():
            raise AssertionError(f"missing shell route: {route}")

    print("NODE52_APP_SHELL_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
