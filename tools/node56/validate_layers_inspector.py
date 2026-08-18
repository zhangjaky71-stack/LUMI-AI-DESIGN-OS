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
        "packages/canvas-sdk/src/controller.ts",
        "commitBatch(descriptors: readonly OperationDescriptor[])",
        "this.gateway.commitBatch(descriptors)",
    )
    require(
        "apps/web/src/lib/layers/model.ts",
        "flattenLayerRows",
        "virtualLayerWindow",
        "LAYER_OVERSCAN = 8",
        "matchingWithAncestors",
        "constraintBadges",
        "brandBindings",
    )
    require(
        "apps/web/src/components/canvas/layer-tree.tsx",
        "ResizeObserver",
        "virtualLayerWindow",
        "Search name, role, kind",
        "onSelect(row.id",
        'property: "visible"',
        'property: "locked"',
        'property: "name"',
    )
    require(
        "apps/web/src/components/canvas/design-inspector.tsx",
        "commonValue",
        "onCommitBatch",
        "Mixed locked selection",
        "propertyEditable = canEdit && !anyLocked",
        'type: "MOVE_NODE"',
        'type: "RESIZE_NODE"',
        'type: "ROTATE_NODE"',
        'type: "SET_TEXT"',
        "Server NODE-39 validation remains authoritative",
        "never silently detaches a brand token",
    )
    require(
        "apps/web/src/components/canvas/infinite-canvas.tsx",
        "localDocument",
        "syncLocalDocument",
        "commitBatch",
        "<LayerTree",
        "<DesignInspector",
        "selectFromLayer",
        'autosave.saveState !== "saved"',
        "documentVersion: projection.revision",
    )
    forbid(
        "apps/web/src/lib/layers/model.ts",
        "localStorage",
        "sessionStorage",
    )
    for path in (
        "apps/web/src/lib/layers/model.test.ts",
        "packages/canvas-sdk/tests/canvas-node56.test.ts",
    ):
        assert (ROOT / path).is_file(), f"missing test: {path}"

    spec = read("docs/nodes/NODE-56-LAYERS-INSPECTOR.md")
    assert "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE" in spec
    print("NODE56_LAYERS_INSPECTOR_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()