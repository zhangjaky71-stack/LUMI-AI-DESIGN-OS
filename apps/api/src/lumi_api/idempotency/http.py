from __future__ import annotations

from collections.abc import Mapping

from .gateway import GatewayResponse, IdempotencyError

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENT_REPLAYED_HEADER = "Idempotent-Replayed"


def extract_idempotency_key(headers: Mapping[str, str]) -> str:
    value = next(
        (header_value for name, header_value in headers.items() if name.lower() == "idempotency-key"),
        "",
    ).strip()
    if not value or len(value) > 512:
        raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
    return value


def replay_headers(response: GatewayResponse) -> dict[str, str]:
    if response.replayed:
        return {IDEMPOTENT_REPLAYED_HEADER: "true"}
    return {}


def error_payload(error: IdempotencyError) -> dict[str, object]:
    return {
        "error": {
            "code": error.code,
            "message": str(error),
            "retryable": error.code == "IDEMPOTENCY_OPERATION_IN_PROGRESS",
        }
    }
