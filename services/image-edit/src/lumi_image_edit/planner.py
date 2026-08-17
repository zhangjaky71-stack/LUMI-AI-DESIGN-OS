from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .model import EditPlan, ImageEditSpec, StructuralEditOperation

STRUCTURAL = {
    "MOVE_TEXT": "MOVE_NODE",
    "RESIZE_TEXT": "RESIZE_NODE",
    "SET_TEXT": "SET_TEXT",
    "CHANGE_COLOR": "SET_PROPERTY",
    "CHANGE_FONT": "SET_PROPERTY",
    "REPLACE_IMAGE_ASSET": "REPLACE_ASSET",
    "REORDER_LAYER": "REORDER_NODE",
    "REPARENT_LAYER": "REPARENT_NODE",
    "BACKGROUND_COLOR": "SET_PROPERTY",
    "APPLY_STYLE": "APPLY_STYLE",
}


def _id(spec: ImageEditSpec) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{spec.organization_id}:{spec.operation_id}:structural",
        )
    )


def _payload(spec: ImageEditSpec, kind: str) -> dict[str, object]:
    value = spec.intent.value
    if kind == "SET_TEXT":
        return {"content": value}
    if kind == "SET_PROPERTY":
        prop = (
            "fill"
            if spec.intent.action in {"CHANGE_COLOR", "BACKGROUND_COLOR"}
            else "font_asset_id"
        )
        return {"property": prop, "value": value}
    if kind == "REPLACE_ASSET":
        return {"asset_id": value}
    if kind == "MOVE_NODE":
        if not isinstance(value, dict):
            raise ValueError("IMAGE_EDIT_MOVE_PAYLOAD_INVALID")
        return {"x": value.get("x"), "y": value.get("y")}
    if kind == "RESIZE_NODE":
        if not isinstance(value, dict):
            raise ValueError("IMAGE_EDIT_RESIZE_PAYLOAD_INVALID")
        return {"width": value.get("width"), "height": value.get("height")}
    if kind == "REORDER_NODE":
        return {"index": value}
    if kind == "REPARENT_NODE":
        return {"parent_id": value}
    if kind == "APPLY_STYLE":
        return {"style_refs": list(value or ())}
    raise ValueError("IMAGE_EDIT_STRUCTURAL_PAYLOAD_UNSUPPORTED")


def _pixel_capabilities(*, hard_protected: bool) -> tuple[str, ...]:
    capabilities = ["image.mask_edit"]
    if hard_protected:
        capabilities.append("image.reference_consistency")
    return tuple(capabilities)


def plan_edit(spec: ImageEditSpec) -> EditPlan:
    kind = STRUCTURAL.get(spec.intent.action)
    if kind and spec.intent.selected_node_ids:
        if spec.design_document_id is None or spec.design_document_version is None:
            raise ValueError("IMAGE_EDIT_STRUCTURAL_DESIGN_VERSION_REQUIRED")
        operation = StructuralEditOperation(
            _id(spec),
            kind,
            spec.intent.selected_node_ids,
            spec.design_document_version,
            _payload(spec, kind),
            f"STRUCTURAL_FIRST:{spec.intent.action}",
        )
        return EditPlan(
            "STRUCTURAL_IR_EDIT",
            ("STRUCTURAL_OPERATION_AVAILABLE", "NO_MODEL_REQUIRED"),
            (operation,),
        )

    hard_protected = any(
        region.severity == "HARD" for region in spec.protected_regions
    )
    if spec.intent.action == "OUTPAINT":
        if not spec.mask:
            raise ValueError("IMAGE_EDIT_OUTPAINT_MASK_REQUIRED")
        return EditPlan(
            "REGENERATE_REGION",
            ("OUTPAINT_REGION", "MINIMUM_EDIT_SURFACE"),
            required_capabilities=_pixel_capabilities(
                hard_protected=hard_protected
            ),
            requires_provider=True,
            requires_mask=True,
        )
    if spec.mask:
        return EditPlan(
            "PIXEL_LOCAL_EDIT",
            ("PIXEL_CONTENT_CHANGE_REQUIRED", "MINIMUM_EDIT_SURFACE"),
            required_capabilities=_pixel_capabilities(
                hard_protected=hard_protected
            ),
            requires_provider=True,
            requires_mask=True,
        )
    if spec.intent.allow_broad_change:
        capabilities = ["image.edit"]
        if hard_protected:
            capabilities.append("image.reference_consistency")
        return EditPlan(
            "FULL_IMAGE_EDIT",
            ("USER_ALLOWED_BROAD_CHANGE",),
            required_capabilities=tuple(capabilities),
            requires_provider=True,
            requires_user_confirmation=(
                hard_protected and not spec.intent.broad_change_confirmed
            ),
        )
    return EditPlan(
        "HYBRID",
        ("SAFE_MASK_OR_COMPOSITE_REQUIRED",),
        required_capabilities=(
            "image.mask_edit",
            "image.reference_consistency",
        ),
        requires_provider=True,
        requires_mask=True,
        requires_user_confirmation=True,
    )
