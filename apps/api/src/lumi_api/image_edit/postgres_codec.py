from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any

from lumi_image_edit import (
    EditConstraint,
    EditIntent,
    EditJob,
    GatewayEditRequest,
    GatewayEditResult,
    ImageEditSpec,
    MaskSpec,
    PixelRect,
    ProtectedRegion,
    SourceImageRef,
)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "__dataclass_fields__"):
        return _json(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


def encode_spec(spec: ImageEditSpec) -> dict[str, Any]:
    return _json(spec)


def _rect(value: dict[str, Any]) -> PixelRect:
    return PixelRect(
        int(value["x"]),
        int(value["y"]),
        int(value["width"]),
        int(value["height"]),
    )


def _protected(value: dict[str, Any]) -> ProtectedRegion:
    return ProtectedRegion(
        value["region_id"],
        value["role"],
        _rect(value["rect"]),
        value["severity"],
        value["source_checksum_sha256"],
        value.get("identity_id"),
        value.get("expected_text"),
        value.get("expected_qr_payload"),
    )


def decode_spec(value: dict[str, Any]) -> ImageEditSpec:
    source = SourceImageRef(**value["source"])
    raw_mask = value.get("mask")
    mask = None
    if raw_mask:
        mask = MaskSpec(
            raw_mask["mask_id"],
            raw_mask["version"],
            raw_mask["source"],
            raw_mask["source_asset_id"],
            raw_mask["source_asset_version"],
            raw_mask["source_checksum_sha256"],
            int(raw_mask["source_width"]),
            int(raw_mask["source_height"]),
            _rect(raw_mask["editable_rect"]),
            raw_mask["checksum_sha256"],
            raw_mask["durable_ref"],
            bool(raw_mask.get("preview_required", False)),
            raw_mask.get("preview_approved_by"),
        )
    intent = EditIntent(
        action=value["intent"]["action"],
        instruction=value["intent"]["instruction"],
        selected_node_ids=tuple(value["intent"].get("selected_node_ids") or ()),
        value=value["intent"].get("value"),
        allow_broad_change=bool(value["intent"].get("allow_broad_change", False)),
        broad_change_confirmed=bool(
            value["intent"].get("broad_change_confirmed", False)
        ),
        broad_change_confirmed_by=value["intent"].get(
            "broad_change_confirmed_by"
        ),
    )
    constraints = tuple(
        EditConstraint(
            item["constraint_id"],
            item["constraint_type"],
            item["severity"],
            item["snapshot_hash"],
            item.get("parameters") or {},
        )
        for item in value.get("constraints", [])
    )
    protected = tuple(
        _protected(item) for item in value.get("protected_regions", [])
    )
    return ImageEditSpec(
        value["organization_id"],
        value["project_id"],
        value["task_id"],
        value["operation_id"],
        source,
        intent,
        constraints,
        protected,
        mask,
        value.get("brand_rule_set_version"),
        tuple(value.get("identity_requirement_ids") or ()),
        Decimal(value["budget_limit_usd"]),
        value["code_git_sha"],
        value.get("design_document_id"),
        value.get("design_document_version"),
        value.get("selected_node_kind"),
        value.get("agent_run_id"),
        value.get("agent_version"),
        value.get("recipe_version"),
        value.get("skill_versions") or {},
        value.get("seed"),
    )


def encode_job(job: EditJob) -> dict[str, Any]:
    return _json(job)


def decode_job(value: dict[str, Any]) -> EditJob:
    payload = dict(value)
    payload["plan_reason_codes"] = tuple(payload.get("plan_reason_codes") or ())
    return EditJob(**payload)


def encode_request(request: GatewayEditRequest) -> dict[str, Any]:
    return _json(request)


def decode_request(value: dict[str, Any]) -> GatewayEditRequest:
    protected = tuple(
        _protected(item) for item in value.get("protected_regions", [])
    )
    return GatewayEditRequest(
        value["organization_id"],
        value["project_id"],
        value["task_id"],
        value["operation_id"],
        value["edit_id"],
        value["route"],
        value["source_ref"],
        value.get("mask_ref"),
        value["instruction"],
        tuple(value.get("required_capabilities") or ()),
        protected,
        tuple(value.get("reference_asset_refs") or ()),
        Decimal(value["budget_limit_usd"]),
        value.get("seed"),
    )


def encode_result(result: GatewayEditResult) -> dict[str, Any]:
    return _json(result)


def decode_result(value: dict[str, Any]) -> GatewayEditResult:
    amount = (
        Decimal(value["cost_usd"])
        if value.get("cost_usd") is not None
        else None
    )
    return GatewayEditResult(
        value["status"],
        value["provider"],
        value["model"],
        value.get("provider_request_id"),
        value.get("output_ref"),
        value.get("output_mime_type"),
        amount,
        value.get("cost_confidence", "unknown"),
        value.get("pricing_snapshot_id"),
        tuple(value.get("routing_reason_codes") or ()),
        value.get("safety_metadata") or {},
        value.get("model_revision"),
        value.get("registry_snapshot_id"),
        value.get("seed"),
        value.get("finish_reason"),
    )
