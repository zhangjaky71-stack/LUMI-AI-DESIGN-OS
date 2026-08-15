from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import TypeAlias
from uuid import UUID

from pydantic import Field, FiniteFloat, field_validator, model_validator

from lumi_api.domain.ids import new_uuid7

from .nodes import ContainerNode, DesignNode, FrameNode, GroupNode, PageNode
from .primitives import DesignModel, Size2D

JsonScalar: TypeAlias = str | int | FiniteFloat | bool | None


class DesignIRDocument(DesignModel):
    spec_version: str = Field(
        default="lumi.design-ir/1.0", pattern=r"^lumi\.design-ir/1\.0$"
    )
    document_id: UUID
    revision: int = Field(ge=1)
    coordinate_space: str = Field(default="logical_px", pattern=r"^logical_px$")
    pages: tuple[UUID, ...] = Field(min_length=1, max_length=1_000)
    nodes: tuple[DesignNode, ...] = Field(min_length=1, max_length=100_000)
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)

    @field_validator("document_id")
    @classmethod
    def require_uuid7_document_id(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("document_id must be UUIDv7")
        return value

    @field_validator("nodes")
    @classmethod
    def canonicalize_node_order(
        cls, value: tuple[DesignNode, ...]
    ) -> tuple[DesignNode, ...]:
        return tuple(sorted(value, key=lambda node: str(node.id)))

    @model_validator(mode="after")
    def validate_scene_graph(self) -> DesignIRDocument:
        mapping: dict[UUID, DesignNode] = {}
        for node in self.nodes:
            if node.id in mapping:
                raise ValueError(f"duplicate node id: {node.id}")
            mapping[node.id] = node

        if len(set(self.pages)) != len(self.pages):
            raise ValueError("page ids must be unique")

        page_node_ids = {
            node.id for node in self.nodes if isinstance(node, PageNode)
        }
        if set(self.pages) != page_node_ids:
            raise ValueError("pages must list every PageNode exactly once")

        for page_id in self.pages:
            page = mapping.get(page_id)
            if not isinstance(page, PageNode):
                raise ValueError(f"page id does not reference a PageNode: {page_id}")

        reference_counts: Counter[UUID] = Counter()
        for node in self.nodes:
            if isinstance(node, (PageNode, FrameNode, GroupNode)):
                if len(set(node.children)) != len(node.children):
                    raise ValueError(f"container has duplicate child ids: {node.id}")
                for child_id in node.children:
                    child = mapping.get(child_id)
                    if child is None:
                        raise ValueError(
                            f"container {node.id} references missing child {child_id}"
                        )
                    if child.parent_id != node.id:
                        raise ValueError(
                            f"child {child_id} parent_id does not match container {node.id}"
                        )
                    reference_counts[child_id] += 1

        for node in self.nodes:
            if isinstance(node, PageNode):
                if reference_counts[node.id] != 0:
                    raise ValueError("PageNode cannot be a child of another node")
                continue

            if node.parent_id is None:
                raise ValueError(f"non-page node has no parent: {node.id}")
            parent = mapping.get(node.parent_id)
            if not isinstance(parent, (PageNode, FrameNode, GroupNode)):
                raise ValueError(f"node parent is not a container: {node.id}")
            if reference_counts[node.id] != 1:
                raise ValueError(
                    f"node must appear exactly once in parent children: {node.id}"
                )

        visited: set[UUID] = set()
        active: set[UUID] = set()

        def visit(node_id: UUID) -> None:
            if node_id in active:
                raise ValueError(f"scene graph cycle detected at {node_id}")
            if node_id in visited:
                return
            active.add(node_id)
            node = mapping[node_id]
            if isinstance(node, (PageNode, FrameNode, GroupNode)):
                for child_id in node.children:
                    visit(child_id)
            active.remove(node_id)
            visited.add(node_id)

        for page_id in self.pages:
            visit(page_id)

        if visited != set(mapping):
            unreachable = sorted(str(node_id) for node_id in set(mapping) - visited)
            raise ValueError(
                "all nodes must be reachable from a page; unreachable="
                + ",".join(unreachable)
            )

        return self


def node_index(document: DesignIRDocument) -> dict[UUID, DesignNode]:
    return {node.id: node for node in document.nodes}


def canonical_json(document: DesignIRDocument) -> str:
    return json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash_sha256(document: DesignIRDocument) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def empty_document(
    *,
    document_id: UUID | None = None,
    width: float = 1920,
    height: float = 1080,
    page_name: str = "Page 1",
) -> DesignIRDocument:
    page_id = new_uuid7()
    return DesignIRDocument(
        document_id=document_id or new_uuid7(),
        revision=1,
        pages=(page_id,),
        nodes=(
            PageNode(
                id=page_id,
                name=page_name,
                size=Size2D(width=width, height=height),
            ),
        ),
    )
