from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/artifact-history/src"))

from lumi_artifacts import (  # noqa: E402
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactHistory,
    ArtifactHistoryError,
    ArtifactVersion,
    CrossTenantLineageError,
    LineageCycleError,
    LineageEdge,
    ProvenanceRecord,
    RightsRecord,
    StorageObjectState,
    build_export_manifest,
    confirm_delete,
    inherit_rights,
    mark_unreferenced,
    sweep_candidates,
)

H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
GIT_SHA = "a" * 40
NOW = datetime(2026, 8, 13, 3, 0, tzinfo=UTC)


def version(
    version_id: str,
    *,
    artifact_id: str = "artifact-a",
    branch_id: str = "branch-main",
    organization_id: str = "org-a",
    parent: str | None = None,
    number: int = 1,
    content_hash: str = H1,
    constraint_hash: str = H2,
    status: str = "DRAFT",
) -> ArtifactVersion:
    return ArtifactVersion(
        id=version_id,
        organization_id=organization_id,
        artifact_id=artifact_id,
        branch_id=branch_id,
        parent_version_id=parent,
        schema_version="1.0",
        version_number=number,
        status=status,  # type: ignore[arg-type]
        content_hash=content_hash,
        constraint_snapshot_hash=constraint_hash,
        created_by_type="AGENT",
        created_by_id="agent-design",
        created_at=NOW + timedelta(seconds=number),
    )


def base_history() -> ArtifactHistory:
    history = ArtifactHistory()
    history.add_artifact(
        Artifact(
            id="artifact-a",
            organization_id="org-a",
            project_id="project-a",
            type="DESIGN_DOCUMENT",
            title="Campaign Poster A",
        )
    )
    history.add_branch(
        ArtifactBranch(
            id="branch-main",
            organization_id="org-a",
            artifact_id="artifact-a",
            name="main",
            base_version_id=None,
            head_version_id=None,
            created_by="user-a",
        )
    )
    return history


class ArtifactHistoryTests(unittest.TestCase):
    def test_version_content_is_frozen_and_branch_head_advances(self) -> None:
        history = base_history()
        v1 = version("v1")
        history.add_version(v1)
        self.assertEqual(history.branches["branch-main"].head_version_id, "v1")
        with self.assertRaises(FrozenInstanceError):
            v1.content_hash = H3  # type: ignore[misc]

    def test_approval_requires_ready_and_required_validation(self) -> None:
        history = base_history()
        history.add_version(version("v1"))
        with self.assertRaises(ArtifactHistoryError):
            history.transition_status("v1", "APPROVED", required_validation_passed=True)
        ready = history.transition_status("v1", "READY")
        self.assertEqual(ready.status, "READY")
        with self.assertRaises(ArtifactHistoryError):
            history.transition_status("v1", "APPROVED", required_validation_passed=False)
        approved = history.transition_status(
            "v1", "APPROVED", required_validation_passed=True, quality_score=0.97
        )
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.content_hash, H1)
        self.assertEqual(approved.constraint_snapshot_hash, H2)

    def test_fork_and_restore_create_new_history_nodes(self) -> None:
        history = base_history()
        history.add_version(version("v1", number=1))
        history.add_version(version("v2", parent="v1", number=2, content_hash=H3))
        fork = history.fork_branch(
            branch_id="branch-alt",
            artifact_id="artifact-a",
            name="alt-dark",
            from_version_id="v1",
            created_by="user-a",
        )
        self.assertEqual(fork.base_version_id, "v1")
        self.assertEqual(fork.head_version_id, "v1")

        restored = history.restore_version(
            source_version_id="v1",
            branch_id="branch-main",
            new_version_id="v3",
            new_version_number=3,
            constraint_snapshot_hash=H2,
            created_by_type="USER",
            created_by_id="user-a",
            created_at=NOW + timedelta(seconds=30),
            lineage_edge_id="edge-restore",
        )
        self.assertEqual(restored.content_hash, history.versions["v1"].content_hash)
        self.assertEqual(restored.parent_version_id, "v2")
        self.assertEqual(history.branches["branch-main"].head_version_id, "v3")
        self.assertEqual(history.lineage_parents("v3")[0].id, "v1")
        self.assertEqual(history.versions["v1"].version_number, 1)

    def test_lineage_supports_multi_parent_and_rejects_cycle(self) -> None:
        history = base_history()
        history.add_version(version("v1", number=1))
        history.add_version(version("v2", parent="v1", number=2, content_hash=H3))

        history.add_artifact(
            Artifact(
                id="artifact-b",
                organization_id="org-a",
                project_id="project-a",
                type="RASTER_IMAGE",
                title="Generated background",
            )
        )
        history.add_branch(
            ArtifactBranch(
                id="branch-b",
                organization_id="org-a",
                artifact_id="artifact-b",
                name="main",
                base_version_id=None,
                head_version_id=None,
                created_by="agent-design",
            )
        )
        history.add_version(
            version(
                "bg-v1",
                artifact_id="artifact-b",
                branch_id="branch-b",
                number=1,
                content_hash="4" * 64,
            )
        )
        history.add_edge(LineageEdge("edge-1", "org-a", "v1", "v2", "EDITED_FROM"))
        history.add_edge(LineageEdge("edge-2", "org-a", "bg-v1", "v2", "COMPOSED_FROM"))
        self.assertEqual({item.id for item in history.lineage_parents("v2")}, {"v1", "bg-v1"})
        with self.assertRaises(LineageCycleError):
            history.add_edge(LineageEdge("edge-cycle", "org-a", "v2", "v1", "DERIVED_FROM"))

    def test_cross_tenant_lineage_is_rejected(self) -> None:
        history = base_history()
        history.add_version(version("v1"))
        history.add_artifact(
            Artifact("artifact-x", "org-x", "project-x", "RASTER_IMAGE", "Other tenant")
        )
        history.add_branch(
            ArtifactBranch("branch-x", "org-x", "artifact-x", "main", None, None, "user-x")
        )
        history.add_version(
            version(
                "x-v1",
                artifact_id="artifact-x",
                branch_id="branch-x",
                organization_id="org-x",
            )
        )
        with self.assertRaises(CrossTenantLineageError):
            history.add_edge(LineageEdge("edge-x", "org-a", "x-v1", "v1", "REFERENCE_USED"))

    def test_content_hash_dedupe_does_not_collapse_version_history(self) -> None:
        history = base_history()
        history.add_version(version("v1", number=1, content_hash=H1))
        history.add_version(version("v2", parent="v1", number=2, content_hash=H1))
        matches = history.find_versions_by_content_hash("org-a", H1)
        self.assertEqual([item.id for item in matches], ["v1", "v2"])
        self.assertNotEqual(matches[0].id, matches[1].id)

    def test_provenance_is_immutable_and_matches_constraint_snapshot(self) -> None:
        history = base_history()
        history.add_version(version("v1"))
        record = ProvenanceRecord(
            artifact_version_id="v1",
            organization_id="org-a",
            constraint_snapshot_hash=H2,
            code_git_sha=GIT_SHA,
            agent_run_id="run-1",
            task_id="task-1",
            generation_id="gen-1",
            provider="provider-a",
            model="model-a",
            provider_request_id="provider-request-1",
            prompt_hash=H3,
            prompt_template_version="poster@1",
            input_asset_ids=("asset-logo", "asset-product"),
            input_artifact_version_ids=("bg-v1",),
            design_ir_schema_version="1.0",
            recipe_version="poster-recipe@1",
            skill_versions={"poster-design": "1.2.0"},
        )
        history.add_provenance(record)
        self.assertEqual(history.provenance["v1"].model, "model-a")
        with self.assertRaises(ArtifactHistoryError):
            history.add_provenance(record)

    def test_rights_inheritance_is_conservative(self) -> None:
        owned = RightsRecord(
            "ASSET", "asset-owned", "org-a", "USER_UPLOAD", "user owns source", "OWNED",
            "ALLOWED", "ALLOWED", "DENIED", False, None, "ASSERTED"
        )
        restricted = RightsRecord(
            "ASSET", "asset-third-party", "org-a", "THIRD_PARTY", None, "NONCOMMERCIAL",
            "DENIED", "UNKNOWN", "UNKNOWN", True, "license-ref", "RESTRICTED"
        )
        result = inherit_rights((owned, restricted), artifact_version_id="v1", organization_id="org-a")
        self.assertEqual(result.commercial_use, "DENIED")
        self.assertEqual(result.redistribution, "UNKNOWN")
        self.assertEqual(result.training_use, "DENIED")
        self.assertEqual(result.license_type, "UNKNOWN")
        self.assertTrue(result.attribution_required)
        self.assertEqual(result.review_status, "RESTRICTED")

    def test_gc_never_deletes_live_retained_or_legal_hold_object(self) -> None:
        live = StorageObjectState("artifacts/live.png")
        unreferenced = StorageObjectState("artifacts/old.png")
        legal = StorageObjectState("artifacts/legal.png", legal_hold=True)
        retained = StorageObjectState("artifacts/retained.png", retention_until=NOW + timedelta(days=7))
        marked = mark_unreferenced(
            (live, unreferenced, legal, retained),
            live_storage_keys={"artifacts/live.png"},
            now=NOW,
        )
        by_key = {item.storage_key: item for item in marked}
        self.assertIsNone(by_key["artifacts/live.png"].marked_at)
        self.assertIsNotNone(by_key["artifacts/old.png"].marked_at)
        self.assertIsNone(by_key["artifacts/legal.png"].marked_at)
        self.assertIsNone(by_key["artifacts/retained.png"].marked_at)

        later = NOW + timedelta(days=2)
        candidates = sweep_candidates(
            marked,
            live_storage_keys={"artifacts/live.png"},
            now=later,
            minimum_mark_delay=timedelta(days=1),
        )
        self.assertEqual([item.storage_key for item in candidates], ["artifacts/old.png"])
        self.assertFalse(
            confirm_delete(
                candidates[0],
                current_live_storage_keys={"artifacts/old.png"},
                now=later,
                minimum_mark_delay=timedelta(days=1),
            )
        )

    def test_export_manifest_contains_traceability_without_secret_prompt(self) -> None:
        history = base_history()
        history.add_version(version("v1"))
        file = ArtifactFile(
            id="file-1",
            organization_id="org-a",
            artifact_version_id="v1",
            role="ORIGINAL",
            storage_key="artifacts/v1/original.png",
            mime_type="image/png",
            size_bytes=2048,
            checksum_sha256=H3,
            width=750,
            height=1624,
        )
        history.add_file(file)
        provenance = ProvenanceRecord(
            artifact_version_id="v1",
            organization_id="org-a",
            constraint_snapshot_hash=H2,
            code_git_sha=GIT_SHA,
            provider="provider-a",
            model="image-model-a",
            prompt_hash=H1,
            input_asset_ids=("asset-logo",),
        )
        rights = RightsRecord(
            "ARTIFACT_VERSION", "v1", "org-a", "GENERATED", None, "UNKNOWN",
            "UNKNOWN", "UNKNOWN", "UNKNOWN", False, None, "UNREVIEWED"
        )
        manifest = build_export_manifest(
            history.versions["v1"], provenance, (file,), (rights,), created_at=NOW
        )
        self.assertEqual(manifest["artifact_version"], "v1")
        self.assertEqual(manifest["checksums"][0]["sha256"], H3)
        self.assertEqual(manifest["constraint_snapshot_hash"], H2)
        self.assertNotIn("prompt", manifest)
        self.assertNotIn("prompt_hash", manifest)
        self.assertNotIn("provider_request_id", manifest)


if __name__ == "__main__":
    unittest.main()
