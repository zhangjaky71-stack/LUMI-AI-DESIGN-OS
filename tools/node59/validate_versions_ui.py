from __future__ import annotations

import json
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
        "version_history_router",
        "app.include_router(version_history_router",
    )
    require(
        "apps/api/src/lumi_api/api/v1/version_history_routes.py",
        '"/artifacts/{artifact_id}/version-history"',
        '"/artifact-versions/{version_id}/provenance-safe"',
        '"/artifact-versions/{version_id}/fork-user"',
        '"/artifact-versions/{version_id}/restore-user"',
        "created_by_type=CreatedByType.USER",
        "created_by_id=_actor_id(request)",
        "expected_head_version_id=body.expected_head_version_id",
        "input_artifact_version_ids=(source.id,)",
        "return _history_item",
    )
    forbid(
        "apps/api/src/lumi_api/api/v1/version_history_routes.py",
        "body.provenance",
        "body.created_by_type",
        "body.created_by_id",
    )
    require(
        "apps/api/src/lumi_api/api/v1/artifact_engine_schemas.py",
        "class VersionArtifactSummary",
        "class ArtifactVersionHistoryItem",
        "class SafeVersionProvenanceResponse",
        "class UserForkVersionRequest",
        "class UserRestoreVersionRequest",
    )
    schema = read("apps/api/src/lumi_api/api/v1/artifact_engine_schemas.py")
    safe_block = schema.split("class SafeVersionProvenanceResponse", 1)[1]
    assert "prompt_ref" not in safe_block
    assert "provider_request_id" not in safe_block
    require(
        "apps/web/src/lib/versions/security.ts",
        "prompt_ref",
        "provider_request_id",
        "reasoning",
        "VERSION_PROVENANCE_PRIVATE_FIELD_FORBIDDEN",
    )
    require(
        "apps/web/src/lib/versions/types.ts",
        "parseVersionHistory",
        "parseSafeVersionProvenance",
        "parseVersionCompare",
        "semanticChanges",
        "nodes_added",
        "properties_changed",
        "text_changed",
        "geometry_changed",
        "asset_replaced",
        "constraints_changed",
    )
    require(
        "apps/web/src/lib/versions/state.ts",
        "branchHeadSnapshot",
        "detectNewHead",
    )
    require(
        "apps/web/src/components/versions/version-history-panel.tsx",
        "branchHeadSnapshot",
        "detectNewHead",
        "Restore creates a new version",
        "Open new head",
        "Exact compare",
        "Visual overlay/wipe is not simulated",
        "Raw prompts, system prompts, provider request IDs",
    )
    forbid(
        "apps/web/src/components/versions/version-history-panel.tsx",
        "JSON.stringify",
        "prompt_ref",
        "provider_request_id",
        "storage_key",
    )
    require(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "VersionHistoryPanel",
        "artifact={selectedArtifact}",
        "onOpenVersion={setSelectedArtifact}",
    )
    for path in (
        "apps/api/tests/test_node59_versions_ui_contracts.py",
        "apps/web/src/lib/versions/types.test.ts",
        "docs/runtime/VERSION-HISTORY-UI-V1.md",
        "reports/nodes/NODE-59/acceptance.md",
        "reports/nodes/NODE-59/gap-ledger.json",
    ):
        assert (ROOT / path).is_file(), f"missing NODE-59 evidence: {path}"

    ledger = json.loads(read("reports/nodes/NODE-59/gap-ledger.json"))
    assert ledger["node"] == "NODE-59"
    assert ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE"
    assert any(item["severity"] == "P0" and item["status"] == "open" for item in ledger["gaps"])
    spec = read("docs/nodes/NODE-59-VERSIONS-UI.md")
    assert "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE" in spec
    print("NODE59_VERSIONS_UI_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
