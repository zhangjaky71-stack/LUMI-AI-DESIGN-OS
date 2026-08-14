from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .model import EditPlan, ImageEditSpec, StructuralEditOperation

_STRUCTURAL_ACTIONS = {
    "MOVE_TEXT": "MOVE_NODE",
    "RESIZE_TEXT": "RESIZE_NODE",
    "SET_TEXT": "SET_TEXT",
    "CHANGE_COLOR": "SET_PROPERTY",
    "CHANGE_FONT": "SET_PROPERTY",
    "REPLACE_IMAGE_ASSET": "REPLACE_ASSET",
    "REORDER_LAYER": "REORDER_NODE",
    "REPARENT_LAYER": "REPARENT_NODE",
    "BACKGROUND_COLOR": "SET_PROPERTY",
}


def _op_id(spec: ImageEditSpec, suffix: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{spec.organization_id}:{spec.operation_id}:{suffix}"))


def _structural_payload(spec: ImageEditSpec, op_type: str) -> dict[str, object]:
    if op_type == "SET_TEXT":
        return {"text": spec.intent.value}
    if op_type == "SET_PROPERTY":
        path = "fill" if spec.intent.action in {"CHANGE_COLOR", "BACKGROUND_COLOR"} else "font_asset_id"
        return {"path": path, "value": spec.intent.value}
    if op_type == "REPLACE_ASSET":
        return {"asset_ref": spec.intent.value}
    if op_type == "MOVE_NODE":
        return {"delta": spec.intent.value}
    if op_type == "RESIZE_NODE":
        return {"size": spec.intent.value}
    if op_type in {"REORDER_NODE", "REPARENT_NODE"}:
        return {"value": spec.intent.value}
    raise ValueError("IMAGE_EDIT_STRUCTURAL_PAYLOAD_UNSUPPORTED")


def plan_edit(spec: ImageEditSpec) -> EditPlan:
    structural_type = _STRUCTURAL_ACTIONS.get(spec.intent.action)
    if structural_type is not None and spec.intent.selected_node_ids:
        if spec.design_document_id is None or spec.design_document_version is None:
            raise ValueError("IMAGE_EDIT_STRUCTURAL_DESIGN_VERSION_REQUIRED")
        operation = StructuralEditOperation(
            operation_id=_op_id(spec, "structural"),
            type=structural_type,  # type: ignore[arg-type]
            target_ids=spec.intent.selected_node_ids,
            expected_document_version=spec.design_document_version,
            payload=_structural_payload(spec, structural_type),
            reason=f"IMAGE_EDIT_STRUCTURAL_FIRST:{spec.intent.action}",
        )
        return EditPlan(
            route="STRUCTURAL_IR_EDIT",
            reason_codes=("STRUCTURAL_OPERATION_AVAILABLE", "NO_MODEL_REQUIRED"),
            structural_operations=(operation,),
        )

    if spec.intent.action == "OUTPAINT":
        if spec.mask is None:
            raise ValueError("IMAGE_EDIT_OUTPAINT_MASK_REQUIRED")
        return EditPlan(
            route="REGENERATE_REGION",
            reason_codes=("PIXEL_CONTENT_CHANGE_REQUIRED", "OUTPAINT_REGION"),
            requires_provider=True,
            requires_mask=True,
        )

    if spec.mask is not None:
        return EditPlan(
            route="PIXEL_LOCAL_EDIT",
            reason_codes=("PIXEL_CONTENT_CHANGE_REQUIRED", "MINIMUM_EDIT_SURFACE"),
            requires_provider=True,
            requires_mask=True,
        )

    if spec.intent.allow_broad_change:
        return EditPlan(
            route="FULL_IMAGE_EDIT",
            reason_codes=("PIXEL_CONTENT_CHANGE_REQUIRED", "USER_ALLOWED_BROAD_CHANGE"),
            requires_provider=True,
            requires_user_confirmation=bool(spec.protected_regions),
        )

    return EditPlan(
        route="HYBRID",
        reason_codes=("PIXEL_CONTENT_CHANGE_REQUIRED", "SAFE_MASK_OR_COMPOSITE_REQUIRED"),
        requires_provider=True,
        requires_mask=True,
        requires_user_confirmation=True,
    )
