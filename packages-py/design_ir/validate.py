from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .models import (
    DESIGN_NODE_KINDS,
    DESIGN_OPERATION_TYPES,
    DesignDocument,
    DesignOperation,
    IrIssue,
    IrRuntimeError,
)

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1", "2.0"}


def _finite_walk(value: Any, pointer: str, issues: list[IrIssue]) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        issues.append(IrIssue("IR_SCHEMA_INVALID", "numeric values must be finite", pointer))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _finite_walk(child, f"{pointer}/{index}", issues)
    elif isinstance(value, dict):
        for key, child in value.items():
            safe = str(key).replace("~", "~0").replace("/", "~1")
            _finite_walk(child, f"{pointer}/{safe}", issues)


def validate_document(document: DesignDocument) -> list[IrIssue]:
    issues: list[IrIssue] = []
    if document.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            IrIssue(
                "IR_VERSION_UNSUPPORTED",
                f"unsupported schema version {document.get('schema_version')}",
                "/schema_version",
            )
        )
    if not document.get("document_id") or not document.get("root_id") or not document.get("unit"):
        issues.append(
            IrIssue(
                "IR_SCHEMA_INVALID",
                "document_id, root_id and unit are required",
                "/",
            )
        )
    nodes = document.get("nodes")
    resources = document.get("resources")
    metadata = document.get("metadata")
    if not isinstance(nodes, dict):
        issues.append(IrIssue("IR_SCHEMA_INVALID", "nodes must be an object", "/nodes"))
        return issues
    if not isinstance(resources, dict):
        issues.append(IrIssue("IR_SCHEMA_INVALID", "resources must be an object", "/resources"))
    if not isinstance(metadata, dict):
        issues.append(IrIssue("IR_SCHEMA_INVALID", "metadata must be an object", "/metadata"))

    for node_id, node in nodes.items():
        pointer = f"/nodes/{node_id}"
        if not isinstance(node, dict):
            issues.append(IrIssue("IR_SCHEMA_INVALID", "node must be an object", pointer))
            continue
        if node.get("id") != node_id:
            issues.append(
                IrIssue(
                    "IR_SCHEMA_INVALID",
                    "node map key must equal node.id",
                    f"{pointer}/id",
                    (node_id,),
                )
            )
        kind = node.get("kind")
        if not isinstance(kind, str) or (
            kind not in DESIGN_NODE_KINDS and not kind.startswith("custom:")
        ):
            issues.append(
                IrIssue(
                    "IR_SCHEMA_INVALID",
                    f"unsupported node kind {kind}",
                    f"{pointer}/kind",
                    (node_id,),
                )
            )
        children = node.get("children")
        if not isinstance(children, list) or len(children) != len(set(children)):
            issues.append(
                IrIssue(
                    "IR_SCHEMA_INVALID",
                    "children must be a unique ordered array",
                    f"{pointer}/children",
                    (node_id,),
                )
            )
            continue
        parent_id = node.get("parent_id")
        if parent_id is not None and parent_id not in nodes:
            issues.append(
                IrIssue(
                    "IR_REFERENCE_MISSING",
                    f"parent {parent_id} does not exist",
                    f"{pointer}/parent_id",
                    (node_id,),
                )
            )
        for index, child_id in enumerate(children):
            child = nodes.get(child_id)
            if not isinstance(child, dict):
                issues.append(
                    IrIssue(
                        "IR_REFERENCE_MISSING",
                        f"child {child_id} does not exist",
                        f"{pointer}/children/{index}",
                        (node_id, str(child_id)),
                    )
                )
            elif child.get("parent_id") != node_id:
                issues.append(
                    IrIssue(
                        "IR_SCHEMA_INVALID",
                        f"child {child_id} parent_id must point to {node_id}",
                        f"{pointer}/children/{index}",
                        (node_id, str(child_id)),
                    )
                )

    root_id = document.get("root_id")
    root = nodes.get(root_id) if isinstance(root_id, str) else None
    if not isinstance(root, dict):
        issues.append(IrIssue("IR_REFERENCE_MISSING", "root_id must reference a node", "/root_id"))
    else:
        if root.get("parent_id") is not None or root.get("kind") != "DOCUMENT_ROOT":
            issues.append(
                IrIssue(
                    "IR_SCHEMA_INVALID",
                    "root node must be DOCUMENT_ROOT with parent_id=null",
                    f"/nodes/{root_id}",
                    (root_id,),
                )
            )
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node_id: str) -> None:
            if node_id in visiting:
                issues.append(
                    IrIssue(
                        "IR_GRAPH_CYCLE",
                        f"cycle detected at {node_id}",
                        f"/nodes/{node_id}",
                        (node_id,),
                    )
                )
                return
            if node_id in visited:
                return
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                return
            visiting.add(node_id)
            for child_id in node.get("children", []):
                if isinstance(child_id, str):
                    walk(child_id)
            visiting.remove(node_id)
            visited.add(node_id)

        walk(root_id)
        for node_id in nodes:
            if node_id not in visited:
                issues.append(
                    IrIssue(
                        "IR_REFERENCE_MISSING",
                        f"node {node_id} is not reachable from root",
                        f"/nodes/{node_id}",
                        (node_id,),
                    )
                )

    _finite_walk(document, "", issues)
    return issues


def parse_document(raw: Any) -> DesignDocument:
    if not isinstance(raw, dict):
        raise IrRuntimeError(IrIssue("IR_SCHEMA_INVALID", "document must be an object"))
    candidate = deepcopy(raw)
    issues = validate_document(candidate)
    if issues:
        raise IrRuntimeError(issues[0])
    return candidate


def validate_operation(operation: DesignOperation) -> None:
    if (
        not isinstance(operation, dict)
        or not isinstance(operation.get("operation_id"), str)
        or not operation["operation_id"]
        or operation.get("type") not in DESIGN_OPERATION_TYPES
        or not isinstance(operation.get("expected_document_version"), int)
        or operation["expected_document_version"] < 0
        or not isinstance(operation.get("target_ids"), list)
        or not isinstance(operation.get("payload"), dict)
    ):
        raise IrRuntimeError(
            IrIssue(
                "IR_OPERATION_INVALID",
                "operation envelope is invalid",
                operation_id=operation.get("operation_id") if isinstance(operation, dict) else None,
            )
        )
    finite: list[IrIssue] = []
    _finite_walk(operation["payload"], "/payload", finite)
    if finite:
        raise IrRuntimeError(
            IrIssue(
                "IR_OPERATION_INVALID",
                finite[0].message,
                finite[0].pointer,
                operation_id=operation["operation_id"],
            )
        )
