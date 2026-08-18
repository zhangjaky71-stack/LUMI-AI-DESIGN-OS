from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "apps/api/src/lumi_api/api/v1/app.py").read_text(encoding="utf-8")


def main() -> None:
    markers = (
        "app.add_middleware(IdempotencyReplayMiddleware)",
        "install_http_security(app, environment=runtime_environment)",
        "install_error_contract(app)",
        "_install_final_security_headers(app, environment=runtime_environment)",
    )
    positions = [APP.index(marker) for marker in markers]
    if positions != sorted(positions):
        raise SystemExit(
            "NODE67_MIDDLEWARE_ORDER_INVALID: expected add-order "
            "Idempotency -> Security -> RequestTrace -> FinalHeaders so Starlette "
            "runtime order is FinalHeaders -> RequestTrace -> Security -> Idempotency -> Route"
        )
    if "Starlette's most recently added user middleware is outermost" not in APP:
        raise SystemExit("NODE67_MIDDLEWARE_ORDER_COMMENT_MISSING")
    print("NODE67_MIDDLEWARE_ORDER_PASS")


if __name__ == "__main__":
    main()
