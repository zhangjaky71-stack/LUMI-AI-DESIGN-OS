from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, FiniteFloat, field_validator

from .primitives import (
    DesignModel,
    NormalizedRect,
    Paint,
    ShadowEffect,
    Size2D,
    StrokeStyle,
    TextStyle,
    Transform2D,
)


class NodeBase(DesignModel):
    id: UUID
    kind: str
    name: str = Field(min_length=1, max_length=240)
    parent_id: UUID | None
    visible: bool = True
    locked: bool = False
    opacity: FiniteFloat = Field(default=1, ge=0, le=1)
    transform: Transform2D = Transform2D()
    semantic_tags: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("node id must be UUIDv7")
        return value

    @field_validator("semantic_tags")
    @classmethod
    def normalize_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(tag.strip() for tag in value)
        if any(not tag or len(tag) > 80 for tag in normalized):
            raise ValueError("semantic tags must be non-empty and <= 80 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("semantic tags must be unique")
        return normalized


class PageNode(NodeBase):
    kind: Literal["page"] = "page"
    parent_id: None = None
    size: Size2D
    background: Paint | None = None
    children: tuple[UUID, ...] = ()


class FrameNode(NodeBase):
    kind: Literal["frame"] = "frame"
    parent_id: UUID
    size: Size2D
    children: tuple[UUID, ...] = ()
    clip_content: bool = False
    fill: Paint | None = None
    stroke: StrokeStyle | None = None
    corner_radius: FiniteFloat = Field(default=0, ge=0, le=100_000)
    shadows: tuple[ShadowEffect, ...] = Field(default=(), max_length=16)


class GroupNode(NodeBase):
    kind: Literal["group"] = "group"
    parent_id: UUID
    children: tuple[UUID, ...] = ()


class TextNode(NodeBase):
    kind: Literal["text"] = "text"
    parent_id: UUID
    size: Size2D
    text: str = Field(max_length=200_000)
    style: TextStyle


class ImageNode(NodeBase):
    kind: Literal["image"] = "image"
    parent_id: UUID
    size: Size2D
    asset_id: UUID
    fit: Literal["cover", "contain", "fill"] = "cover"
    crop: NormalizedRect | None = None


class ShapeNode(NodeBase):
    kind: Literal["shape"] = "shape"
    parent_id: UUID
    shape: Literal["rectangle", "ellipse", "line"]
    size: Size2D
    fill: Paint | None = None
    stroke: StrokeStyle | None = None
    corner_radius: FiniteFloat = Field(default=0, ge=0, le=100_000)


class VectorNode(NodeBase):
    kind: Literal["vector"] = "vector"
    parent_id: UUID
    size: Size2D
    path_data: str = Field(min_length=1, max_length=500_000)
    fill: Paint | None = None
    stroke: StrokeStyle | None = None
    fill_rule: Literal["nonzero", "evenodd"] = "nonzero"


DesignNode = Annotated[
    PageNode | FrameNode | GroupNode | TextNode | ImageNode | ShapeNode | VectorNode,
    Field(discriminator="kind"),
]

ContainerNode = PageNode | FrameNode | GroupNode
SizedNode = PageNode | FrameNode | TextNode | ImageNode | ShapeNode | VectorNode
PaintableNode = FrameNode | ShapeNode | VectorNode
