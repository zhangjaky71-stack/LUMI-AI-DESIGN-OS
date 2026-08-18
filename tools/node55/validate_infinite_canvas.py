from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *markers: str) -> None:
    text = read(path)
    missing = [marker for marker in markers if marker not in text]
    assert not missing, f"{path}: missing {missing}"


def forbid(path: str, *markers: str) -> None:
    text = read(path)
    found = [marker for marker in markers if marker in text]
    assert not found, f"{path}: forbidden {found}"


def main() -> None:
    require(
        "apps/api/src/lumi_api/api/v1/app.py",
        "canvas_document_router",
        "app.include_router(canvas_document_router",
    )
    require(
        "apps/api/src/lumi_api/api/v1/canvas_document_routes.py",
        '"/design-documents/{design_document_id}/canvas"',
        '"/artifact-versions/{artifact_version_id}/canvas"',
        '"/design-documents/{design_document_id}/commands"',
    )
    require(
        "apps/api/src/lumi_api/api/v1/canvas_document_dependencies.py",
        "canvas_document_service_factory",
        "with factory() as service",
    )
    forbid(
        "apps/api/src/lumi_api/api/v1/canvas_document_dependencies.py",
        'getattr(request.app.state, "canvas_document_service", None)',
    )
    require(
        "apps/api/src/lumi_api/api/v1/canvas_document_adapter.py",
        "FOR UPDATE",
        "expected_design_document_version_id",
        "CANVAS_REVISION_CONFLICT",
        "canvas_last_client_batch_id",
        "content_hash_sha256(updated_document)",
        "UPDATE design_documents",
        "head_version_id=:expected_head",
        'descriptor.type == "MOVE_NODE"',
        'descriptor.payload.get("x")',
        'descriptor.type == "ROTATE_NODE"',
    )
    require(
        "apps/api/src/lumi_api/api/v1/canvas_document_factory.py",
        "session = self.session_factory()",
        "session.close()",
    )

    require(
        "packages/canvas-sdk/src/operation-gateway.ts",
        "OperationCommittedListener",
        "this.onCommitted?.([descriptor], result)",
        "this.onCommitted?.(descriptors, result)",
    )
    require(
        "packages/canvas-sdk/src/controller.ts",
        "onOperationCommitted?: OperationCommittedListener",
    )

    require(
        "apps/web/src/lib/api/client.ts",
        'browserCookie("lumi_csrf")',
        'headers.set("x-csrf-token", csrf)',
    )
    require(
        "apps/web/src/lib/canvas/types.ts",
        'value === "lumi.design-ir/1.0"',
        "node.parent_id = rootId",
        'descriptor.type === "CREATE_NODE"',
        'descriptor.type === "SET_PROPERTY"',
        "recursive: true",
    )
    require(
        "apps/web/src/lib/canvas/use-autosave.ts",
        "MAX_PENDING_COMMANDS = 120",
        "AUTOSAVE_DELAY_MS = 700",
        "activeBatchRef",
        "error.status === 409",
        'setSaveState("conflict")',
        "beforeunload",
    )
    forbid(
        "apps/web/src/lib/canvas/use-autosave.ts",
        "localStorage",
        "sessionStorage",
    )
    require(
        "apps/web/src/components/canvas/infinite-canvas.tsx",
        "new CanvasController",
        'beginTransform("move"',
        "controller.selectAt",
        "controller.pan",
        "controller.zoomToCursor",
        "getCanvasHead",
        "Reload canonical",
        "onSelectionChange?.({",
        'autosave.saveState !== "saved"',
    )
    require(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "<InfiniteCanvas",
        "setCanvasSelection",
        "canvasContextReady",
        'canvasSaveState === "saved"',
        "selection: canvasSelection",
    )

    for path in (
        "packages/canvas-sdk/tests/canvas-node55.test.ts",
        "apps/web/src/lib/canvas/types.test.ts",
        "apps/api/tests/test_node55_canvas_document_contracts.py",
    ):
        assert (ROOT / path).is_file(), f"missing test: {path}"

    print("NODE55_INFINITE_CANVAS_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
