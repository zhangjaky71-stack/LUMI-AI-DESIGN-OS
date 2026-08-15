from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_api.design_ir.document import (
    DesignIRDocument,
    canonical_json,
    content_hash_sha256,
    empty_document,
    node_index,
)
from lumi_api.design_ir.engine import OperationRejected, RevisionConflict, apply_batch
from lumi_api.design_ir.nodes import FrameNode, PageNode, TextNode
from lumi_api.design_ir.operations import (
    ActorRef,
    AddNodeOp,
    DesignOperationBatch,
    MoveNodeOp,
    RemoveNodeOp,
    SetFillOp,
    SetLockOp,
    SetTextOp,
)
from lumi_api.design_ir.primitives import RgbaColor, Size2D, SolidPaint, TextStyle
from lumi_api.domain.ids import new_uuid7


@pytest.fixture
def document() -> DesignIRDocument:
    return empty_document(width=750, height=1624)


def text_node(parent_id: UUID, *, text: str = "Hello") -> TextNode:
    return TextNode(
        id=new_uuid7(),
        name="Headline",
        parent_id=parent_id,
        size=Size2D(width=400, height=100),
        text=text,
        style=TextStyle(
            font_family="Inter",
            font_size=48,
            color=RgbaColor(r=0.1, g=0.1, b=0.1, a=1),
        ),
    )


def batch(
    document: DesignIRDocument,
    *operations: object,
) -> DesignOperationBatch:
    return DesignOperationBatch(
        operation_id=new_uuid7(),
        document_id=document.document_id,
        base_revision=document.revision,
        actor=ActorRef(kind="agent", actor_id="design-agent.v1"),
        operations=operations,  # type: ignore[arg-type]
    )


def test_empty_document_has_one_valid_page_and_stable_hash(
    document: DesignIRDocument,
) -> None:
    assert document.spec_version == "lumi.design-ir/1.0"
    assert document.coordinate_space == "logical_px"
    assert document.revision == 1
    assert len(document.pages) == 1
    assert isinstance(node_index(document)[document.pages[0]], PageNode)
    assert len(content_hash_sha256(document)) == 64
    assert canonical_json(document) == canonical_json(document)


def test_add_text_is_atomic_and_increments_revision_once(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    node = text_node(page_id)
    result = apply_batch(
        document,
        batch(document, AddNodeOp(parent_id=page_id, index=0, node=node)),
    )

    assert document.revision == 1
    assert result.previous_revision == 1
    assert result.new_revision == 2
    assert result.document.revision == 2
    updated = node_index(result.document)
    assert updated[node.id] == node
    page = updated[page_id]
    assert isinstance(page, PageNode)
    assert page.children == (node.id,)


def test_multiple_operations_commit_as_one_revision(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    node = text_node(page_id)
    operation_batch = batch(
        document,
        AddNodeOp(parent_id=page_id, index=0, node=node),
        SetTextOp(node_id=node.id, text="Updated by agent"),
    )
    result = apply_batch(document, operation_batch)

    assert result.new_revision == document.revision + 1
    updated = node_index(result.document)[node.id]
    assert isinstance(updated, TextNode)
    assert updated.text == "Updated by agent"


def test_revision_conflict_rejects_stale_batch_without_mutating_document(
    document: DesignIRDocument,
) -> None:
    before = canonical_json(document)
    stale = DesignOperationBatch(
        operation_id=new_uuid7(),
        document_id=document.document_id,
        base_revision=document.revision + 1,
        actor=ActorRef(kind="user", actor_id="user-1"),
        operations=(SetLockOp(node_id=document.pages[0], locked=True),),
    )

    with pytest.raises(RevisionConflict):
        apply_batch(document, stale)
    assert canonical_json(document) == before


def test_failed_later_operation_rolls_back_entire_batch_in_memory(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    node = text_node(page_id)
    before = canonical_json(document)
    invalid = batch(
        document,
        AddNodeOp(parent_id=page_id, index=0, node=node),
        SetFillOp(
            node_id=node.id,
            fill=SolidPaint(color=RgbaColor(r=1, g=0, b=0, a=1)),
        ),
    )

    with pytest.raises(OperationRejected):
        apply_batch(document, invalid)
    assert canonical_json(document) == before
    assert node.id not in node_index(document)


def test_scene_graph_rejects_missing_child_reference(
    document: DesignIRDocument,
) -> None:
    page = node_index(document)[document.pages[0]]
    assert isinstance(page, PageNode)
    missing = new_uuid7()

    with pytest.raises(ValidationError):
        DesignIRDocument(
            document_id=document.document_id,
            revision=1,
            pages=document.pages,
            nodes=(page.model_copy(update={"children": (missing,)}),),
        )


def test_nested_frame_text_and_move_preserve_single_parent(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    frame = FrameNode(
        id=new_uuid7(),
        name="Hero",
        parent_id=page_id,
        size=Size2D(width=600, height=600),
    )
    text = text_node(frame.id)
    created = apply_batch(
        document,
        batch(
            document,
            AddNodeOp(parent_id=page_id, index=0, node=frame),
            AddNodeOp(parent_id=frame.id, index=0, node=text),
        ),
    ).document

    moved = apply_batch(
        created,
        batch(
            created,
            MoveNodeOp(node_id=text.id, new_parent_id=page_id, index=1),
        ),
    ).document
    mapping = node_index(moved)
    moved_text = mapping[text.id]
    moved_frame = mapping[frame.id]
    page = mapping[page_id]

    assert isinstance(moved_text, TextNode)
    assert moved_text.parent_id == page_id
    assert isinstance(moved_frame, FrameNode)
    assert moved_frame.children == ()
    assert isinstance(page, PageNode)
    assert page.children == (frame.id, text.id)


def test_recursive_remove_deletes_subtree_but_not_page(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    frame = FrameNode(
        id=new_uuid7(),
        name="Group Frame",
        parent_id=page_id,
        size=Size2D(width=300, height=300),
    )
    text = text_node(frame.id)
    created = apply_batch(
        document,
        batch(
            document,
            AddNodeOp(parent_id=page_id, index=0, node=frame),
            AddNodeOp(parent_id=frame.id, index=0, node=text),
        ),
    ).document

    with pytest.raises(OperationRejected):
        apply_batch(created, batch(created, RemoveNodeOp(node_id=frame.id)))

    removed = apply_batch(
        created,
        batch(created, RemoveNodeOp(node_id=frame.id, recursive=True)),
    ).document
    mapping = node_index(removed)
    assert frame.id not in mapping
    assert text.id not in mapping
    assert page_id in mapping


def test_locked_node_blocks_content_edit_but_can_be_unlocked(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    node = text_node(page_id)
    created = apply_batch(
        document,
        batch(
            document,
            AddNodeOp(parent_id=page_id, index=0, node=node),
            SetLockOp(node_id=node.id, locked=True),
        ),
    ).document

    with pytest.raises(OperationRejected):
        apply_batch(
            created,
            batch(created, SetTextOp(node_id=node.id, text="blocked")),
        )

    unlocked = apply_batch(
        created,
        batch(created, SetLockOp(node_id=node.id, locked=False)),
    ).document
    changed = apply_batch(
        unlocked,
        batch(unlocked, SetTextOp(node_id=node.id, text="allowed")),
    ).document
    final_node = node_index(changed)[node.id]
    assert isinstance(final_node, TextNode)
    assert final_node.text == "allowed"


def test_nodes_are_canonicalized_independent_of_tuple_input_order(
    document: DesignIRDocument,
) -> None:
    page_id = document.pages[0]
    page = node_index(document)[page_id]
    assert isinstance(page, PageNode)
    node = text_node(page_id)
    page_with_child = page.model_copy(update={"children": (node.id,)})

    first = DesignIRDocument(
        document_id=document.document_id,
        revision=1,
        pages=(page_id,),
        nodes=(page_with_child, node),
    )
    second = DesignIRDocument(
        document_id=document.document_id,
        revision=1,
        pages=(page_id,),
        nodes=(node, page_with_child),
    )
    assert canonical_json(first) == canonical_json(second)
    assert content_hash_sha256(first) == content_hash_sha256(second)


def test_operation_schema_rejects_unknown_fields_and_non_uuid7_operation_id(
    document: DesignIRDocument,
) -> None:
    with pytest.raises(ValidationError):
        DesignOperationBatch.model_validate(
            {
                "operation_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_id": str(document.document_id),
                "base_revision": 1,
                "actor": {"kind": "system"},
                "operations": [
                    {
                        "op": "set_lock",
                        "node_id": str(document.pages[0]),
                        "locked": True,
                        "unexpected": "not allowed",
                    }
                ],
            }
        )


def test_design_ir_has_no_renderer_orm_or_agent_runtime_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "lumi_api" / "design_ir"
    forbidden = {
        "pixi",
        "pixijs",
        "sqlalchemy",
        "asyncpg",
        "alembic",
        "langgraph",
        "langchain",
        "openai",
        "anthropic",
        "boto3",
    }
    discovered: set[str] = set()

    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in item.names)
            elif isinstance(item, ast.ImportFrom) and item.module:
                discovered.add(item.module.split(".")[0])

    assert discovered.isdisjoint(forbidden)
