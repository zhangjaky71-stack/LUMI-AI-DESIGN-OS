from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from lumi_model_gateway import (
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelResult,
    ResultStatus,
    Timing,
    Usage,
)

from lumi_api.model_paid_guard import (
    _decode_model_result,
    _encode_model_result,
    _pack,
    _paid_operation_key,
)


def _result() -> ModelResult:
    marker = uuid4()
    return ModelResult(
        status=ResultStatus.SUCCEEDED,
        provider="fixture-provider",
        model="fixture-model",
        provider_request_id="provider-request-123",
        outputs=(
            ModelOutput(
                kind="json",
                value={
                    "score": Decimal("0.12500000"),
                    "marker": marker,
                    "sequence": ("a", 2, True),
                    "nested": [1, {"ratio": 0.5}],
                },
                mime_type="application/json",
            ),
        ),
        usage=Usage(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cached_input_tokens=2,
            image_input_tokens=0,
            image_output_tokens=0,
            seconds=Decimal("1.250"),
            units={"images": Decimal("1")},
        ),
        timing=Timing(total_ms=1250, ttft_ms=80, queue_ms=15),
        cost=CostEstimate(
            amount_usd=Decimal("0.01230000"),
            confidence=CostConfidence.EXACT,
            price_snapshot_id="pricing-v1",
            detail={
                "input": Decimal("0.0023"),
                "output": Decimal("0.0100"),
                "version": 1,
            },
        ),
        safety_metadata={"policy": "allow", "score": Decimal("0.01")},
        finish_reason="stop",
        raw_response_ref="provider://response/123",
    )


def test_model_result_codec_round_trips_without_loss() -> None:
    original = _result()
    encoded = _encode_model_result(original)
    replayed = _decode_model_result(encoded)
    assert replayed == original


def test_paid_operation_key_is_stable_but_provider_model_scoped() -> None:
    operation_id = uuid4()
    first = _paid_operation_key(operation_id, "provider-a", "model-a")
    assert first == _paid_operation_key(operation_id, "provider-a", "model-a")
    assert first != _paid_operation_key(operation_id, "provider-b", "model-a")
    assert first != _paid_operation_key(operation_id, "provider-a", "model-b")
    assert first.startswith(f"model-paid:{operation_id}:")
    assert len(first) < 512


def test_durable_codec_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="NON_FINITE_FLOAT"):
        _pack(float("nan"))
    with pytest.raises(ValueError, match="NON_FINITE_DECIMAL"):
        _pack(Decimal("Infinity"))


def test_decoder_rejects_unknown_schema_version() -> None:
    encoded = _encode_model_result(_result())
    encoded["schema_version"] = 999
    with pytest.raises(ValueError, match="RESULT_SCHEMA_UNSUPPORTED"):
        _decode_model_result(encoded)
