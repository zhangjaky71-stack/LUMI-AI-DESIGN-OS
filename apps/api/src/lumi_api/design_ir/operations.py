from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, FiniteFloat, field_validator, model_validator

from .nodes import DesignNode
from .primitives import DesignModel, NormalizedRect, Paint, Size2D, StrokeStyle, TextStyle, Transform2D


class ActorRef(DesignModel):
    kind: Literal["user", "agent", "system"]
    actor_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_non_system_actor_id(self) -> ActorRef:
        if self.kind != "system" and not self.actor_id:
            raise ValueError("user/agent actor requires actor_id")
        return self


class AddNodeOp(DesignModel):
    op: Literal["add_node"] = "add_node"
    parent_id: UUID
    index: int = Field(ge=0)
    node: DesignNode


class RemoveNodeOp(DesignModel):
    op: Literal["remove_node"] = "remove_node"
    node_id: UUID
    recursive: bool = False


class MoveNodeOp(DesignModel):
    op: Literal["move_node"] = "move_node"
    node_id: UUID
    new_parent_id: UUID
    index: int = Field(ge=0)


class ReorderChildrenOp(DesignModel):
    op: Literal["reorder_children"] = "reorder_children"
    parent_id: UUID
    child_ids: tuple[UUID, ...]


class SetTransformOp(DesignModel):
    op: Literal["set_transform"] = "set_transform"
    node_id: UUID
    transform: Transform2D


class SetSizeOp(DesignModel):
    op: Literal["set_size"] = "set_size"
    node_id: UUID
    size: Size2D


class SetAppearanceOp(DesignModel):
    op: Literal["set_appearance"] = "set_appearance"
    node_id: UUID
    visible: bool | None = None
    opacity: FiniteFloat | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_change(self) -> SetAppearanceOp:
        if self.visible is None and self.opacity is None:
            raise ValueError("set_appearance requires visible and/or opacity")
        return self


class SetLockOp(DesignModel):
    op: Literal["set_lock"] = "set_lock"
    node_id: UUID
    locked: bool


class RenameNodeOp(DesignModel):
    op: Literal["rename_node"] = "rename_node"
    node_id: UUID
    name: str = Field(min_length=1, max_length=240)


class SetTextOp(DesignModel):
    op: Literal["set_text"] = "set_text"
    node_id: UUID
    text: str = Field(max_length=200_000)


class SetTextStyleOp(DesignModel):
    op: Literal["set_text_style"] = "set_text_style"
    node_id: UUID
    style: TextStyle


class SetImageAssetOp(DesignModel):
    op: Literal["set_image_asset"] = "set_image_asset"
    node_id: UUID
    asset_id: UUID


class SetImageCropOp(DesignModel):
    op: Literal["set_image_crop"] = "set_image_crop"
    node_id: UUID
    crop: NormalizedRect | None = None


class SetFillOp(DesignModel):
    op: Literal["set_fill"] = "set_fill"
    node_id: UUID
    fill: Paint | None = None


class SetStrokeOp(DesignModel):
    op: Literal["set_stroke"] = "set_stroke"
    node_id: UUID
    stroke: StrokeStyle | None = None


class SetPageBackgroundOp(DesignModel):
    op: Literal["set_page_background"] = "set_page_background"
    node_id: UUID
    background: Paint | None = None


DesignOperation = Annotated[
    AddNodeOp
    | RemoveNodeOp
    | MoveNodeOp
    | ReorderChildrenOp
    | SetTransformOp
    | SetSizeOp
    | SetAppearanceOp
    | SetLockOp
    | RenameNodeOp
    | SetTextOp
    | SetTextStyleOp
    | SetImageAssetOp
    | SetImageCropOp
    | SetFillOp
    | SetStrokeOp
    | SetPageBackgroundOp,
    Field(discriminator="op"),
]


class DesignOperationBatch(DesignModel):
    schema_version: str = Field(
        default="lumi.design-op/1.0", pattern=r"^lumi\.design-op/1\.0$"
    )
    operation_id: UUID
    document_id: UUID
    base_revision: int = Field(ge=1)
    actor: ActorRef
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    operations: tuple[DesignOperation, ...] = Field(min_length=1, max_length=1_000)

    @field_validator("operation_id")
    @classmethod
    def require_uuid7_operation_id(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("operation_id must be UUIDv7")
        return value
