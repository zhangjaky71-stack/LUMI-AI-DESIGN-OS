from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
DesignDocument = dict[str, Any]
DesignOperation = dict[str, Any]

DESIGN_NODE_KINDS = {
    "DOCUMENT_ROOT",
    "FRAME",
    "GROUP",
    "TEXT",
    "IMAGE",
    "SHAPE",
    "VECTOR_PATH",
    "VIDEO",
    "MASK",
    "GUIDE",
    "COMPONENT",
    "INSTANCE",
}

DESIGN_OPERATION_TYPES = {
    "CREATE_NODE",
    "DELETE_NODE",
    "SET_PROPERTY",
    "MOVE_NODE",
    "RESIZE_NODE",
    "ROTATE_NODE",
    "REORDER_NODE",
    "REPARENT_NODE",
    "REPLACE_ASSET",
    "SET_TEXT",
    "APPLY_STYLE",
    "BATCH",
}


@dataclass(frozen=True, slots=True)
class IrIssue:
    code: str
    message: str
    pointer: str | None = None
    node_ids: tuple[str, ...] = ()
    operation_id: str | None = None


class IrRuntimeError(ValueError):
    def __init__(self, issue: IrIssue) -> None:
        super().__init__(f"{issue.code}: {issue.message}")
        self.issue = issue
        self.code = issue.code
        self.pointer = issue.pointer
        self.node_ids = issue.node_ids
        self.operation_id = issue.operation_id


ConstraintPreflight = Callable[[DesignDocument, DesignOperation], list[IrIssue]]


@dataclass(frozen=True, slots=True)
class OperationExecution:
    document: DesignDocument
    previous_version: int
    document_version: int
    applied_operation_ids: tuple[str, ...]
    diff: dict[str, list[str]]
