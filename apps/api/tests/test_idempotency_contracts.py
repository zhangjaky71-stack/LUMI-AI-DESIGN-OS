from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
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
from lumi_api.idempotency.gateway import GatewayResponse, OperationHandle
from lumi_api.idempotency.http import extract_idempotency_key, replay_headers
from lumi_api.idempotency.policy import DEFAULT_COMPENSATION, GATEWAY_REQUIRED_SIDE_EFFECTS
from lumi_api.persistence.models import IdempotencyOperation


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
    changed = {**right, "prompt": "different"}
    assert canonical_request_hash(left) != canonical_request_hash(changed)


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

    response = GatewayResponse(
        operation_id=uuid4(),
        replayed=True,
        result_ref=None,
        result_json={},
        response_status=200,
    )
    assert replay_headers(response) == {"Idempotent-Replayed": "true"}


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


def test_paid_provider_crash_barrier_is_pinned_in_orm_and_operation_handle() -> None:
    columns = IdempotencyOperation.__table__.columns
    assert "provider_attempt_started_at" in columns
    assert columns["provider_attempt_started_at"].nullable is True
    assert callable(getattr(OperationHandle, "mark_provider_attempt_started", None))


def test_provider_attempt_barrier_migration_follows_current_release_head() -> None:
    api_root = Path(__file__).resolve().parents[1]
    migration = api_root / "alembic" / "versions" / "0019_side_effect_provider_attempt_barrier.py"
    source = migration.read_text(encoding="utf-8")
    assert 'revision = "0019_side_effect_provider_attempt_barrier"' in source
    assert 'down_revision = "0018_platform_provider_cost_guard"' in source
    assert "ADD COLUMN provider_attempt_started_at timestamptz" in source
