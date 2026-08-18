from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "apps/api/src/lumi_api/api/v1/app.py").read_text(encoding="utf-8")
IDEMPOTENCY = (ROOT / "apps/api/src/lumi_api/api/v1/idempotency_middleware.py").read_text(
    encoding="utf-8"
)


def main() -> None:
    # Starlette's most recently added user middleware is outermost. The source add
    # order below therefore produces runtime order:
    # IdempotencyReplay -> RequestId/Trace -> SecurityHTTP -> Route.
    markers = (
        "install_http_security(app, environment=runtime_environment)",
        "install_error_contract(app)",
        "app.add_middleware(IdempotencyReplayMiddleware)",
    )
    positions = [APP.index(marker) for marker in markers]
    if positions != sorted(positions):
        raise SystemExit(
            "NODE67_MIDDLEWARE_ORDER_INVALID: expected add-order "
            "Security -> RequestTrace -> Idempotency so runtime order is "
            "Idempotency -> RequestTrace -> Security -> Route"
        )
    if "Starlette's most recently added user middleware is outermost" not in APP:
        raise SystemExit("NODE67_MIDDLEWARE_ORDER_COMMENT_MISSING")
    if "_install_final_security_headers" in APP:
        raise SystemExit("NODE67_PHANTOM_FINAL_SECURITY_LAYER_FORBIDDEN")
    # The outer idempotency middleware is safe in front of the security gate only
    # because it always calls the next layer and does not synthesize a cached response.
    if "response = await call_next(request)" not in IDEMPOTENCY:
        raise SystemExit("NODE67_IDEMPOTENCY_MIDDLEWARE_MUST_CALL_SECURITY_LAYER")
    print("NODE67_MIDDLEWARE_ORDER_PASS")


if __name__ == "__main__":
    main()
