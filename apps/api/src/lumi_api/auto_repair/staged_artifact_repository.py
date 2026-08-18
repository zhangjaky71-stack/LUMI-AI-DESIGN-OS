from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from lumi_api.artifact_engine.contracts import (
    ArtifactOutboxEvent,
    ProvenanceCompleteness,
    ProvenanceEnvelope,
)
from lumi_api.artifact_engine.ports import ArtifactHeadConflict, ArtifactNotFound
from lumi_api.artifact_engine.postgres_repository import PostgresArtifactRepository
from lumi_api.artifacts.models import ArtifactVersion, ArtifactVersionStatus, LineageEdge


class PostgresStagedArtifactRepository(PostgresArtifactRepository):
    """NODE-42 extension for exact-version quality gates before head advancement."""

    def stage_version(
        self,
        *,
        branch_id: UUID,
        expected_head_version_id: UUID | None,
        version_factory: Any,
        lineage_factory: Any,
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        event_factory: Any,
    ) -> tuple[ArtifactVersion, tuple[LineageEdge, ...]]:
        with self._transaction():
            row = self._one(
                """
                SELECT id, organization_id, artifact_id, name, base_version_id,
                       head_version_id, created_by_type, created_by_id, created_at
                FROM artifact_branches
                WHERE id=:id AND organization_id=:organization_id
                FOR UPDATE
                """,
                {"id": branch_id, "organization_id": self.organization_id},
                label=f"branch {branch_id} not found",
            )
            branch = self._branch(row)
            if branch.head_version_id != expected_head_version_id:
                raise ArtifactHeadConflict(
                    "branch head changed before stage: "
                    f"expected={expected_head_version_id} actual={branch.head_version_id}"
                )
            next_number = self.session.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM artifact_versions
                    WHERE branch_id=:branch_id AND organization_id=:organization_id
                    """
                ),
                {"branch_id": branch_id, "organization_id": self.organization_id},
            ).scalar_one()
            version = version_factory(branch, int(next_number))
            self._assert_org(version.organization_id)
            if version.parent_version_id != expected_head_version_id:
                raise ValueError("staged version parent must be expected branch head")
            if version.primary_file_id is not None and version.primary_file_id not in {
                item.id for item in version.files
            }:
                raise ValueError("primary_file_id must reference a staged version file")
            edges = tuple(lineage_factory(version))
            for edge in edges:
                self._assert_org(edge.organization_id)
                source_exists = self.session.execute(
                    text(
                        "SELECT 1 FROM artifact_versions "
                        "WHERE id=:id AND organization_id=:organization_id"
                    ),
                    {
                        "id": edge.source_artifact_version_id,
                        "organization_id": self.organization_id,
                    },
                ).scalar_one_or_none()
                if source_exists is None:
                    raise ArtifactNotFound(
                        f"lineage source {edge.source_artifact_version_id} not found"
                    )
            self._insert_version_record(version, completeness)
            for item in version.files:
                self._insert_file(version, item)
            if version.primary_file_id is not None:
                self.session.execute(
                    text(
                        "UPDATE artifact_versions SET primary_file_id=:file_id "
                        "WHERE id=:version_id"
                    ),
                    {"file_id": version.primary_file_id, "version_id": version.id},
                )
            for edge in edges:
                self._insert_edge(edge)
            self._insert_provenance(version.id, provenance, completeness)
            self._insert_outbox(event_factory(version))
            return version, edges

    def advance_head_to_staged(
        self,
        *,
        branch_id: UUID,
        expected_head_version_id: UUID | None,
        staged_version_id: UUID,
        event: ArtifactOutboxEvent,
    ) -> None:
        with self._transaction():
            branch = self._one(
                """
                SELECT id, artifact_id, head_version_id
                FROM artifact_branches
                WHERE id=:id AND organization_id=:organization_id
                FOR UPDATE
                """,
                {"id": branch_id, "organization_id": self.organization_id},
                label=f"branch {branch_id} not found",
            )
            if branch["head_version_id"] != expected_head_version_id:
                raise ArtifactHeadConflict(
                    "branch head changed before staged promotion: "
                    f"expected={expected_head_version_id} actual={branch['head_version_id']}"
                )
            staged = self._one(
                """
                SELECT id, artifact_id, branch_id, parent_version_id, status
                FROM artifact_versions
                WHERE id=:id AND organization_id=:organization_id
                FOR UPDATE
                """,
                {
                    "id": staged_version_id,
                    "organization_id": self.organization_id,
                },
                label=f"staged version {staged_version_id} not found",
            )
            if staged["artifact_id"] != branch["artifact_id"] or staged["branch_id"] != branch_id:
                raise ValueError("staged version must belong to target branch/artifact")
            if staged["parent_version_id"] != expected_head_version_id:
                raise ArtifactHeadConflict("staged version parent no longer matches expected head")
            if str(staged["status"]).lower() != ArtifactVersionStatus.APPROVED.value.lower():
                raise ValueError("staged version must be APPROVED before head promotion")
            updated = self.session.execute(
                text(
                    """
                    UPDATE artifact_branches
                    SET head_version_id=:version_id, updated_at=:updated_at, version=version+1
                    WHERE id=:branch_id AND organization_id=:organization_id
                      AND head_version_id IS NOT DISTINCT FROM :expected_head
                    """
                ),
                {
                    "version_id": staged_version_id,
                    "updated_at": event.occurred_at,
                    "branch_id": branch_id,
                    "organization_id": self.organization_id,
                    "expected_head": expected_head_version_id,
                },
            )
            if updated.rowcount != 1:
                raise ArtifactHeadConflict("branch head changed during staged promotion")
            self._insert_outbox(event)
