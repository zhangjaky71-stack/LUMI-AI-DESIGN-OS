from __future__ import annotations

from enum import StrEnum

from .contracts import CompensationStrategy


class SideEffectKind(StrEnum):
    PAID_MODEL_INVOCATION = "paid_model_invocation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    EXTERNAL_TOOL_WRITE = "external_tool_write"
    OBJECT_FINALIZATION = "object_finalization"
    BILLING_CHARGE = "billing_charge"
    BILLING_CREDIT = "billing_credit"
    EMAIL_SEND = "email_send"
    INVITE_SEND = "invite_send"
    EXPORT_CREATION = "export_creation"
    EXTERNAL_PUBLISH = "external_publish"


GATEWAY_REQUIRED_SIDE_EFFECTS = frozenset(SideEffectKind)

DEFAULT_COMPENSATION: dict[SideEffectKind, CompensationStrategy] = {
    SideEffectKind.PAID_MODEL_INVOCATION: CompensationStrategy.NON_COMPENSATABLE,
    SideEffectKind.IMAGE_GENERATION: CompensationStrategy.NON_COMPENSATABLE,
    SideEffectKind.VIDEO_GENERATION: CompensationStrategy.NON_COMPENSATABLE,
    SideEffectKind.EXTERNAL_TOOL_WRITE: CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION,
    SideEffectKind.OBJECT_FINALIZATION: CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION,
    SideEffectKind.BILLING_CHARGE: CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION,
    SideEffectKind.BILLING_CREDIT: CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION,
    SideEffectKind.EMAIL_SEND: CompensationStrategy.NON_COMPENSATABLE,
    SideEffectKind.INVITE_SEND: CompensationStrategy.NON_COMPENSATABLE,
    SideEffectKind.EXPORT_CREATION: CompensationStrategy.COMPENSATABLE,
    SideEffectKind.EXTERNAL_PUBLISH: CompensationStrategy.REVERSIBLE_BY_NEW_OPERATION,
}
