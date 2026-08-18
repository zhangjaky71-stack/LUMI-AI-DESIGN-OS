from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from lumi_model_gateway import (
    CostConfidence,
    CostEstimate,
    DeliveryState,
    ErrorCategory,
    ModelOutput,
    ModelRequest,
    ModelResult,
    ProviderInvocationError,
    ResultStatus,
    Timing,
    Usage,
)

from .idempotency import (
    AmbiguousSideEffectError,
    IdempotencyContext,
    OperationHandle,
    RetryableSideEffectError,
    SideEffectGateway,
    SideEffectResult,
)
from .idempotency.gateway import IdempotencyError

_RESULT_SCHEMA_VERSION = 1
_OPERATION_TYPE = "paid_model_invocation"
_DEFAULT_LEASE_SECONDS = 900


class PostgresModelPaidInvocationGuard:
    """NODE-20-backed paid invocation guard for the hosted Model Gateway.

    The guard persists a provider-attempt barrier before the first outbound
    provider call. A process crash after that point but before a provider
    request id is durably bound fails closed on the next claim instead of
    repeating a potentially billable request.
    """

    def __init__(
        self,
        database_dsn: str,
        *,
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    ) -> None:
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("MODEL_PAID_GUARD_LEASE_SECONDS_INVALID")
        self._gateway = SideEffectGateway(_asyncpg_dsn(database_dsn))
        self._lease_seconds = lease_seconds

    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult:
        context = IdempotencyContext(
            organization_id=request.organization_id,
            operation_type=_OPERATION_TYPE,
            idempotency_key=_paid_operation_key(request.operation_id, provider, model),
            request={
                "operation_id": request.operation_id,
                "semantic_input_hash": request.semantic_hash,
                "provider": provider,
                "model": model,
            },
            business_scope_id=request.operation_id,
            lease_seconds=self._lease_seconds,
        )
        lease_owner = f"model-gateway:{uuid4()}"
        original_provider_error: ProviderInvocationError | None = None

        async def guarded_invoke(handle: OperationHandle) -> SideEffectResult:
            nonlocal original_provider_error
            await handle.mark_provider_attempt_started()
            try:
                result = await invoke()
            except ProviderInvocationError as exc:
                original_provider_error = exc
                if exc.delivery_state == DeliveryState.NOT_ACCEPTED:
                    # This is the only provider classification strong enough to
                    # clear NODE-20's pre-call barrier and permit a safe retry.
                    raise RetryableSideEffectError(
                        exc.category.value,
                        str(exc),
                    ) from exc
                raise

            if result.provider != provider or result.model != model:
                raise RuntimeError("MODEL_PAID_GUARD_RESULT_IDENTITY_MISMATCH")
            if result.provider_request_id:
                await handle.record_provider_request(result.provider_request_id)
            return SideEffectResult(
                result_json=_encode_model_result(result),
                response_status=200,
            )

        try:
            response = await self._gateway.execute(
                context,
                lease_owner=lease_owner,
                invoke=guarded_invoke,
            )
        except RetryableSideEffectError as exc:
            if (
                original_provider_error is not None
                and original_provider_error.delivery_state == DeliveryState.NOT_ACCEPTED
            ):
                raise original_provider_error from exc
            raise _unknown_provider_error(
                provider,
                model,
                "retry-safe idempotency transition lost its provider classification",
            ) from exc
        except AmbiguousSideEffectError as exc:
            if original_provider_error is not None:
                delivery_state = original_provider_error.delivery_state
                if delivery_state == DeliveryState.NOT_ACCEPTED:
                    delivery_state = DeliveryState.UNKNOWN
                raise ProviderInvocationError(
                    original_provider_error.category,
                    str(exc),
                    provider=provider,
                    model=model,
                    delivery_state=delivery_state,
                    retry_after_seconds=original_provider_error.retry_after_seconds,
                    provider_code=original_provider_error.provider_code,
                ) from exc
            raise _unknown_provider_error(provider, model, str(exc)) from exc
        except IdempotencyError as exc:
            # Conflicts, active-lease contention and lease loss are all unsafe
            # to normalize through a provider adapter: none proves that a paid
            # request was not accepted.
            raise _unknown_provider_error(provider, model, str(exc)) from exc

        try:
            result = _decode_model_result(response.result_json)
        except Exception as exc:
            # A corrupted durable replay must never fall through to a new paid
            # invocation. Surface an ambiguous provider outcome instead.
            raise _unknown_provider_error(
                provider,
                model,
                "durable model result replay could not be decoded",
            ) from exc
        if result.provider != provider or result.model != model:
            raise _unknown_provider_error(
                provider,
                model,
                "durable model result replay identity mismatch",
            )
        return result


def _paid_operation_key(operation_id: UUID, provider: str, model: str) -> str:
    identity = hashlib.sha256(
        f"{provider}\x00{model}".encode("utf-8")
    ).hexdigest()[:24]
    return f"model-paid:{operation_id}:{identity}"


def _unknown_provider_error(provider: str, model: str, message: str) -> ProviderInvocationError:
    return ProviderInvocationError(
        ErrorCategory.UNKNOWN,
        message,
        provider=provider,
        model=model,
        delivery_state=DeliveryState.UNKNOWN,
    )


def _asyncpg_dsn(database_dsn: str) -> str:
    return database_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _encode_model_result(result: ModelResult) -> dict[str, Any]:
    return {
        "schema_version": _RESULT_SCHEMA_VERSION,
        "status": result.status.value,
        "provider": result.provider,
        "model": result.model,
        "provider_request_id": result.provider_request_id,
        "outputs": [
            {
                "kind": output.kind,
                "value": _pack(output.value),
                "mime_type": output.mime_type,
            }
            for output in result.outputs
        ],
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "image_input_tokens": result.usage.image_input_tokens,
            "image_output_tokens": result.usage.image_output_tokens,
            "seconds": (
                format(result.usage.seconds, "f")
                if result.usage.seconds is not None
                else None
            ),
            "units": {
                key: format(value, "f") for key, value in result.usage.units.items()
            },
        },
        "timing": {
            "total_ms": result.timing.total_ms,
            "ttft_ms": result.timing.ttft_ms,
            "queue_ms": result.timing.queue_ms,
        },
        "cost": {
            "amount_usd": (
                format(result.cost.amount_usd, "f")
                if result.cost.amount_usd is not None
                else None
            ),
            "confidence": result.cost.confidence.value,
            "price_snapshot_id": result.cost.price_snapshot_id,
            "detail": _pack(result.cost.detail),
        },
        "safety_metadata": _pack(result.safety_metadata),
        "finish_reason": result.finish_reason,
        "raw_response_ref": result.raw_response_ref,
    }


def _decode_model_result(payload: dict[str, Any]) -> ModelResult:
    if payload.get("schema_version") != _RESULT_SCHEMA_VERSION:
        raise ValueError("MODEL_PAID_GUARD_RESULT_SCHEMA_UNSUPPORTED")
    usage_payload = _require_dict(payload, "usage")
    timing_payload = _require_dict(payload, "timing")
    cost_payload = _require_dict(payload, "cost")
    outputs_payload = payload.get("outputs")
    if not isinstance(outputs_payload, list):
        raise ValueError("MODEL_PAID_GUARD_OUTPUTS_INVALID")
    outputs: list[ModelOutput] = []
    for item in outputs_payload:
        if not isinstance(item, dict):
            raise ValueError("MODEL_PAID_GUARD_OUTPUT_INVALID")
        outputs.append(
            ModelOutput(
                kind=_require_str(item, "kind"),
                value=_unpack(item.get("value")),
                mime_type=_optional_str(item.get("mime_type")),
            )
        )

    units_payload = usage_payload.get("units", {})
    if not isinstance(units_payload, dict):
        raise ValueError("MODEL_PAID_GUARD_USAGE_UNITS_INVALID")
    units = {str(key): Decimal(_require_string_value(value)) for key, value in units_payload.items()}

    detail = _unpack(cost_payload.get("detail"))
    if not isinstance(detail, dict):
        raise ValueError("MODEL_PAID_GUARD_COST_DETAIL_INVALID")
    safety_metadata = _unpack(payload.get("safety_metadata"))
    if not isinstance(safety_metadata, dict):
        raise ValueError("MODEL_PAID_GUARD_SAFETY_METADATA_INVALID")

    return ModelResult(
        status=ResultStatus(_require_str(payload, "status")),
        provider=_require_str(payload, "provider"),
        model=_require_str(payload, "model"),
        provider_request_id=_optional_str(payload.get("provider_request_id")),
        outputs=tuple(outputs),
        usage=Usage(
            input_tokens=_optional_int(usage_payload.get("input_tokens")),
            output_tokens=_optional_int(usage_payload.get("output_tokens")),
            total_tokens=_optional_int(usage_payload.get("total_tokens")),
            cached_input_tokens=_optional_int(usage_payload.get("cached_input_tokens")),
            image_input_tokens=_optional_int(usage_payload.get("image_input_tokens")),
            image_output_tokens=_optional_int(usage_payload.get("image_output_tokens")),
            seconds=(
                Decimal(_require_string_value(usage_payload["seconds"]))
                if usage_payload.get("seconds") is not None
                else None
            ),
            units=units,
        ),
        timing=Timing(
            total_ms=_require_int(timing_payload, "total_ms"),
            ttft_ms=_optional_int(timing_payload.get("ttft_ms")),
            queue_ms=_optional_int(timing_payload.get("queue_ms")),
        ),
        cost=CostEstimate(
            amount_usd=(
                Decimal(_require_string_value(cost_payload["amount_usd"]))
                if cost_payload.get("amount_usd") is not None
                else None
            ),
            confidence=CostConfidence(_require_str(cost_payload, "confidence")),
            price_snapshot_id=_optional_str(cost_payload.get("price_snapshot_id")),
            detail=detail,
        ),
        safety_metadata=safety_metadata,
        finish_reason=_optional_str(payload.get("finish_reason")),
        raw_response_ref=_optional_str(payload.get("raw_response_ref")),
    )


def _pack(value: Any) -> dict[str, Any]:
    if value is None:
        return {"t": "null"}
    if isinstance(value, bool):
        return {"t": "bool", "v": value}
    if isinstance(value, int):
        return {"t": "int", "v": value}
    if isinstance(value, float):
        return {"t": "float", "v": value}
    if isinstance(value, str):
        return {"t": "str", "v": value}
    if isinstance(value, Decimal):
        return {"t": "decimal", "v": format(value, "f")}
    if isinstance(value, UUID):
        return {"t": "uuid", "v": str(value)}
    if isinstance(value, (list, tuple)):
        return {"t": "list", "v": [_pack(item) for item in value]}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("MODEL_PAID_GUARD_NON_STRING_DICT_KEY")
        return {
            "t": "dict",
            "v": [[key, _pack(child)] for key, child in value.items()],
        }
    raise TypeError(f"MODEL_PAID_GUARD_UNSUPPORTED_VALUE:{type(value).__name__}")


def _unpack(value: Any) -> Any:
    if not isinstance(value, dict):
        raise ValueError("MODEL_PAID_GUARD_PACKED_VALUE_INVALID")
    kind = value.get("t")
    if kind == "null":
        return None
    if kind == "bool":
        raw = value.get("v")
        if not isinstance(raw, bool):
            raise ValueError("MODEL_PAID_GUARD_BOOL_INVALID")
        return raw
    if kind == "int":
        raw = value.get("v")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError("MODEL_PAID_GUARD_INT_INVALID")
        return raw
    if kind == "float":
        raw = value.get("v")
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError("MODEL_PAID_GUARD_FLOAT_INVALID")
        return float(raw)
    if kind == "str":
        return _require_string_value(value.get("v"))
    if kind == "decimal":
        return Decimal(_require_string_value(value.get("v")))
    if kind == "uuid":
        return UUID(_require_string_value(value.get("v")))
    if kind == "list":
        raw = value.get("v")
        if not isinstance(raw, list):
            raise ValueError("MODEL_PAID_GUARD_LIST_INVALID")
        return [_unpack(item) for item in raw]
    if kind == "dict":
        raw = value.get("v")
        if not isinstance(raw, list):
            raise ValueError("MODEL_PAID_GUARD_DICT_INVALID")
        decoded: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                raise ValueError("MODEL_PAID_GUARD_DICT_ENTRY_INVALID")
            if item[0] in decoded:
                raise ValueError("MODEL_PAID_GUARD_DICT_DUPLICATE_KEY")
            decoded[item[0]] = _unpack(item[1])
        return decoded
    raise ValueError("MODEL_PAID_GUARD_PACKED_TYPE_INVALID")


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"MODEL_PAID_GUARD_{key.upper()}_INVALID")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"MODEL_PAID_GUARD_{key.upper()}_INVALID")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"MODEL_PAID_GUARD_{key.upper()}_INVALID")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("MODEL_PAID_GUARD_OPTIONAL_INT_INVALID")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("MODEL_PAID_GUARD_OPTIONAL_STR_INVALID")
    return value


def _require_string_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("MODEL_PAID_GUARD_STRING_VALUE_INVALID")
    return value
