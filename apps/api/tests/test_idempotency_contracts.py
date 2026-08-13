from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from lumi_api.idempotency.contracts import (
    ClaimDecision,
    CompensationStrategy,
    IdempotencyContext,
    ProviderState,
    canonical_request_hash,
    deterministic_operation_key,
)
from lumi_api.idempotency.http import extract_idempotency_key, replay_headers
from lumi_api.idempotency.policy import DEFAULT_COMPENSATION, GATEWAY_REQUIRED_SIDE_EFFECTS


def test_canonical_request_hash_ignores_transport_trace_fields() -> None:
    left = {
        "prompt": "hello",
        "settings": {"size": 1024, "temperature": Decimal("0.50")},
        "trace_id": "trace-a",
        "request_id": "request-a",
    }
    right = {
        "request_id": "request-b",
        "settings": {"temperature": Decimal("0.50"), "size": 1024},
        "prompt": "hello",
        "trace_id": "trace-b",
    }
    assert canonical_request_hash(left) == canonical_request_hash(right)
    assert canonical_request_hash(left) != canonical_request_hash({**right, "prompt": "different"})


def test_deterministic_operation_key_does_not_include_retry_attempt() -> None:
    project_id = uuid4()
    task_id = uuid4()
    key_a = deterministic_operation_key(project_id, task_id, "slot-1", "policy-v1")
    key_b = deterministic_operation_key(project_id, task_id, "slot-1", "policy-v1")
    assert key_a == key_b
    assert key_a.startswith("op:")


def test_context_validates_key_and_lease() -> None:
    context = IdempotencyContext(
        organization_id=uuid4(),
        operation_type="image.generate",
        idempotency_key="client-key",
        request={"prompt": "x", "when": datetime.now(UTC)},
        lease_seconds=30,
    )
    assert len(context.request_hash) == 64
    with pytest.raises(ValueError, match="KEY_INVALID"):
        IdempotencyContext(uuid4(), "image.generate", "", {})


def test_http_idempotency_header_and_replay_header() -> None:
    assert extract_idempotency_key({"idempotency-key": "abc"}) == "abc"
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REQUIRED"):
        extract_idempotency_key({})

    class Response:
        replayed = True

    assert replay_headers(Response()) == {"Idempotent-Replayed": "true"}


def test_paid_side_effect_policy_is_explicit() -> None:
    values = {effect.value for effect in GATEWAY_REQUIRED_SIDE_EFFECTS}
    assert "paid_model_invocation" in values
    assert "image_generation" in values
    assert "video_generation" in values
    assert "billing_charge" in values
    assert "external_publish" in values
    assert all(effect in DEFAULT_COMPENSATION for effect in GATEWAY_REQUIRED_SIDE_EFFECTS)
    assert CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION in DEFAULT_COMPENSATION.values()


def test_contract_enums_cover_recovery_outcomes() -> None:
    assert ClaimDecision.RECONCILE == "reconcile"
    assert ClaimDecision.RETRY_SAFE == "retry_safe"
    assert ProviderState.UNKNOWN == "unknown"
