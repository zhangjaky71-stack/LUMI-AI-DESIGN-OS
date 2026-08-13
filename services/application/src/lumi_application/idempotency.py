from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .context import ApplicationContext
from .errors import IdempotencyConflict
from .ports import IdempotencyClaim, IdempotencyClaimState, IdempotencyPort


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def claim_operation(
    port: IdempotencyPort,
    context: ApplicationContext,
    *,
    key: str,
    operation_type: str,
    request_hash: str,
) -> IdempotencyClaim:
    if len(key) < 8 or len(key) > 512:
        raise ValueError("idempotency key must contain 8..512 characters")
    claim = await port.claim(
        context,
        key=key,
        operation_type=operation_type,
        request_hash=request_hash,
    )
    if claim.state is IdempotencyClaimState.CONFLICT:
        raise IdempotencyConflict(
            "idempotency key already belongs to a different request or operation"
        )
    if claim.state is IdempotencyClaimState.REPLAY and not claim.result_ref:
        raise IdempotencyConflict("idempotency replay is missing its durable result reference")
    return claim
