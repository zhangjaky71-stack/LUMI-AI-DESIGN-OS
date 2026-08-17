from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7
from lumi_api.artifacts.models import (
    Artifact,
    ArtifactType,
    ArtifactBranch,
    ArtifactFile,
    ArtifactVersion,
    ArtifactVersionStatus,
    CreatedByType,
    FileRole,
    LineageEdge,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
)

from .contracts import (
    ApprovalRecord,
    ArtifactOutboxEvent,
    GcAudit,
    GcMark,
    GcMarkState,
    ProvenanceCompleteness,
    ProvenanceEnvelope,
    TraceabilityStatus,
)
from .ports import ArtifactHeadConflict, ArtifactNotFound


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _provenance_hash(envelope: ProvenanceEnvelope) -> str:
    return hashlib.sha256(_json(envelope).encode("utf-8")).hexdigest()


def _db_status(value: ArtifactVersionStatus | str) -> str:
    raw = value.value if isinstance(value, ArtifactVersionStatus) else value
    return raw.lower()


def _model_status(value: str) -> ArtifactVersionStatus:
    return ArtifactVersionStatus(value.upper())


def _db_creator(value: CreatedByType | str) -> str:
    raw = value.value if isinstance(value, CreatedByType) else value
    return raw.lower()


def _model_creator(value: str) -> CreatedByType:
    return CreatedByType(value.upper())


def _metadata_tuple(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    return tuple(sorted((str(key), str(item)) for key, item in value.items()))


class PostgresArtifactRepository:
    """Tenant-scoped PostgreSQL implementation of the NODE-42 repository port.

    The repository owns a dedicated SQLAlchemy Session and short transactions.
    Branch appends acquire a row lock and compare the expected head before
    allocating the next version number, inserting immutable rows, advancing the
    head, and writing the outbox event. Do not share the Session with another UoW.
    """

    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        # This repository owns its dedicated Session. SQLAlchemy autobegins even
        # for reads, so close any prior read transaction before opening the
        # write transaction. Callers must not share this Session with another UoW.
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def _one(self, sql: str, params: dict[str, Any], *, label: str) -> Mapping[str, Any]:
        row = self.session.execute(text(sql), params).mappings().one_or_none()
        if row is None:
            raise ArtifactNotFound(label)
        return row

    def get_artifact(self, artifact_id: UUID) -> Artifact:
        row = self._one(
            """
            SELECT id, organization_id, project_id, kind, name, design_document_id,
                   rights_json, archived_at, retention_until, legal_hold
            FROM artifacts
            WHERE id=:id AND organization_id=:organization_id AND deleted_at IS NULL
            """,
            {"id": artifact_id, "organization_id": self.organization_id},
            label=f"artifact {artifact_id} not found",
        )
        return Artifact(
            id=row["id"],
            organization_id=row["organization_id"],
            project_id=row["project_id"],
            type=ArtifactType(str(row["kind"]).upper()),
            name=row["name"],
            design_document_id=row["design_document_id"],
            rights=RightsPolicy.model_validate(row["rights_json"]),
            archived_at=row["archived_at"],
            retention_until=row["retention_until"],
            legal_hold=row["legal_hold"],
        )

    def get_branch(self, branch_id: UUID) -> ArtifactBranch:
        row = self._one(
            """
            SELECT id, organization_id, artifact_id, name, base_version_id,
                   head_version_id, created_by_type, created_by_id, created_at
            FROM artifact_branches
            WHERE id=:id AND organization_id=:organization_id
            """,
            {"id": branch_id, "organization_id": self.organization_id},
            label=f"branch {branch_id} not found",
        )
        return self._branch(row)

    def get_version(self, version_id: UUID) -> ArtifactVersion:
        row = self._one(
            """
            SELECT v.*, p.provenance_json
            FROM artifact_versions v
            LEFT JOIN LATERAL (
                SELECT ap.provenance_json
                FROM artifact_provenance ap
                WHERE ap.artifact_version_id=v.id
                  AND ap.organization_id=v.organization_id
                ORDER BY ap.created_at DESC, ap.id DESC
                LIMIT 1
            ) p ON true
            WHERE v.id=:id AND v.organization_id=:organization_id
            """,
            {"id": version_id, "organization_id": self.organization_id},
            label=f"version {version_id} not found",
        )
        files = self._files(version_id)
        return self._version(row, files)

    def list_versions(self, artifact_id: UUID) -> tuple[ArtifactVersion, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT v.*, p.provenance_json
                FROM artifact_versions v
                LEFT JOIN LATERAL (
                    SELECT ap.provenance_json
                    FROM artifact_provenance ap
                    WHERE ap.artifact_version_id=v.id
                      AND ap.organization_id=v.organization_id
                    ORDER BY ap.created_at DESC, ap.id DESC
                    LIMIT 1
                ) p ON true
                WHERE v.artifact_id=:artifact_id AND v.organization_id=:organization_id
                ORDER BY v.branch_id, v.version_number
                """
            ),
            {"artifact_id": artifact_id, "organization_id": self.organization_id},
        ).mappings().all()
        return tuple(self._version(row, self._files(row["id"])) for row in rows)

    def list_lineage(self, version_id: UUID) -> tuple[LineageEdge, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT id, organization_id, from_artifact_version_id,
                       to_artifact_version_id, edge_type, metadata_json, created_at
                FROM artifact_edges
                WHERE to_artifact_version_id=:version_id
                  AND organization_id=:organization_id
                ORDER BY edge_type, from_artifact_version_id
                """
            ),
            {"version_id": version_id, "organization_id": self.organization_id},
        ).mappings().all()
        return tuple(
            LineageEdge(
                id=row["id"],
                organization_id=row["organization_id"],
                artifact_version_id=row["to_artifact_version_id"],
                source_artifact_version_id=row["from_artifact_version_id"],
                type=LineageEdgeType(row["edge_type"]),
                created_at=row["created_at"],
                metadata=_metadata_tuple(row["metadata_json"]),
            )
            for row in rows
        )

    def list_branches(self, artifact_id: UUID) -> tuple[ArtifactBranch, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT id, organization_id, artifact_id, name, base_version_id,
                       head_version_id, created_by_type, created_by_id, created_at
                FROM artifact_branches
                WHERE artifact_id=:artifact_id AND organization_id=:organization_id
                ORDER BY name
                """
            ),
            {"artifact_id": artifact_id, "organization_id": self.organization_id},
        ).mappings().all()
        return tuple(self._branch(row) for row in rows)

    def create_artifact_bundle(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        event: ArtifactOutboxEvent,
    ) -> None:
        self._assert_org(artifact.organization_id)
        self._assert_org(branch.organization_id)
        with self._transaction():
            self._insert_artifact(artifact, branch.created_at)
            self._insert_branch(branch, artifact.project_id)
            self._insert_outbox(event)

    def create_artifact_bundle_with_initial_version(
        self,
        artifact: Artifact,
        branch: ArtifactBranch,
        version: ArtifactVersion,
        lineage: tuple[LineageEdge, ...],
        provenance: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
        events: tuple[ArtifactOutboxEvent, ...],
    ) -> None:
        self._assert_org(artifact.organization_id)
        self._assert_org(branch.organization_id)
        self._assert_org(version.organization_id)
        if version.artifact_id != artifact.id or version.branch_id != branch.id:
            raise ValueError("initial version must belong to the created artifact/main branch")
        if version.version_number != 1 or version.parent_version_id is not None:
            raise ValueError("initial artifact version must be root version number 1")
        if version.primary_file_id is not None and version.primary_file_id not in {
            item.id for item in version.files
        }:
            raise ValueError("primary_file_id must reference a file in the initial version")
        with self._transaction():
            for edge in lineage:
                self._assert_org(edge.organization_id)
                source = self.session.execute(
                    text(
                        "SELECT 1 FROM artifact_versions "
                        "WHERE id=:id AND organization_id=:organization_id"
                    ),
                    {
                        "id": edge.source_artifact_version_id,
                        "organization_id": self.organization_id,
                    },
                ).scalar_one_or_none()
                if source is None:
                    raise ArtifactNotFound(
                        f"lineage source {edge.source_artifact_version_id} not found"
                    )
            self._insert_artifact(artifact, branch.created_at)
            self._insert_branch(branch, artifact.project_id)
            self._insert_version_record(version, completeness)
            for item in version.files:
                self._insert_file(version, item)
            if version.primary_file_id is not None:
                self.session.execute(
                    text(
                        "UPDATE artifact_versions SET primary_file_id=:file_id WHERE id=:version_id"
                    ),
                    {"file_id": version.primary_file_id, "version_id": version.id},
                )
            for edge in lineage:
                self._insert_edge(edge)
            self._insert_provenance(version.id, provenance, completeness)
            self.session.execute(
                text(
                    """
                    UPDATE artifact_branches
                    SET base_version_id=:version_id, head_version_id=:version_id,
                        updated_at=:updated_at, version=version+1
                    WHERE id=:branch_id AND organization_id=:organization_id
                      AND head_version_id IS NULL AND base_version_id IS NULL
                    """
                ),
                {
                    "version_id": version.id,
                    "updated_at": version.created_at,
                    "branch_id": branch.id,
                    "organization_id": self.organization_id,
                },
            )
            for event in events:
                self._insert_outbox(event)

    def create_branch(self, branch: ArtifactBranch, event: ArtifactOutboxEvent) -> None:
        self._assert_org(branch.organization_id)
        with self._transaction():
            artifact = self._one(
                "SELECT project_id FROM artifacts "
                "WHERE id=:id AND organization_id=:organization_id",
                {"id": branch.artifact_id, "organization_id": self.organization_id},
                label=f"artifact {branch.artifact_id} not found",
            )
            self._insert_branch(branch, artifact["project_id"])
            self._insert_outbox(event)

    def append_version(
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
                    "branch head changed: "
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
            if version.primary_file_id is not None and version.primary_file_id not in {
                item.id for item in version.files
            }:
                raise ValueError("primary_file_id must reference a file in the new version")
            edges = tuple(lineage_factory(version))
            for edge in edges:
                self._assert_org(edge.organization_id)
                source = self.session.execute(
                    text(
                        "SELECT 1 FROM artifact_versions "
                        "WHERE id=:id AND organization_id=:organization_id"
                    ),
                    {
                        "id": edge.source_artifact_version_id,
                        "organization_id": self.organization_id,
                    },
                ).scalar_one_or_none()
                if source is None:
                    raise ArtifactNotFound(
                        f"lineage source {edge.source_artifact_version_id} not found"
                    )

            self._insert_version_record(version, completeness)
            for item in version.files:
                self._insert_file(version, item)
            if version.primary_file_id is not None:
                self.session.execute(
                    text(
                        "UPDATE artifact_versions SET primary_file_id=:file_id WHERE id=:version_id"
                    ),
                    {"file_id": version.primary_file_id, "version_id": version.id},
                )
            for edge in edges:
                self._insert_edge(edge)
            self._insert_provenance(version.id, provenance, completeness)
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
                    "version_id": version.id,
                    "updated_at": version.created_at,
                    "branch_id": branch.id,
                    "organization_id": self.organization_id,
                    "expected_head": expected_head_version_id,
                },
            )
            if updated.rowcount != 1:
                raise ArtifactHeadConflict("branch head changed during append")
            self._insert_outbox(event_factory(version))
            return version, edges

    def replace_version_status(
        self,
        version: ArtifactVersion,
        *,
        expected_status: str,
        approval: ApprovalRecord | None,
        event: ArtifactOutboxEvent,
    ) -> None:
        self._assert_org(version.organization_id)
        with self._transaction():
            result = self.session.execute(
                text(
                    """
                    UPDATE artifact_versions
                    SET status=:next_status
                    WHERE id=:id AND organization_id=:organization_id
                      AND status=:expected_status
                    """
                ),
                {
                    "next_status": _db_status(version.status),
                    "id": version.id,
                    "organization_id": self.organization_id,
                    "expected_status": expected_status.lower(),
                },
            )
            if result.rowcount != 1:
                raise ArtifactHeadConflict(
                    f"version status changed: expected={expected_status}"
                )
            if approval is not None:
                self._insert_approval(approval)
            self._insert_outbox(event)

    def get_provenance_envelope(self, version_id: UUID) -> ProvenanceEnvelope:
        row = self.session.execute(
            text(
                """
                SELECT provenance_json, compiler_version, agent_version
                FROM artifact_provenance
                WHERE artifact_version_id=:version_id
                  AND organization_id=:organization_id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"version_id": version_id, "organization_id": self.organization_id},
        ).mappings().one_or_none()
        if row is None:
            self.get_version(version_id)
            return ProvenanceEnvelope(
                record=ProvenanceRecord(code_git_sha="0" * 40),
                compiler_version=None,
                agent_version=None,
            )
        return ProvenanceEnvelope(
            record=ProvenanceRecord.model_validate(row["provenance_json"]),
            compiler_version=row["compiler_version"],
            agent_version=row["agent_version"],
        )

    def get_provenance_completeness(self, version_id: UUID) -> ProvenanceCompleteness:
        row = self.session.execute(
            text(
                """
                SELECT completeness_status, completeness_score, missing_fields_json
                FROM artifact_provenance
                WHERE artifact_version_id=:version_id
                  AND organization_id=:organization_id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"version_id": version_id, "organization_id": self.organization_id},
        ).mappings().one_or_none()
        if row is None:
            self.get_version(version_id)
            return ProvenanceCompleteness(
                score=0.0,
                status=TraceabilityStatus.PARTIAL,
                missing_fields=("legacy_provenance_record",),
            )
        missing = row["missing_fields_json"] or []
        return ProvenanceCompleteness(
            score=float(row["completeness_score"]),
            status=TraceabilityStatus(row["completeness_status"]),
            missing_fields=tuple(str(item) for item in missing),
        )

    def record_gc_marks(self, marks: tuple[GcMark, ...]) -> None:
        with self._transaction():
            for mark in marks:
                self._assert_org(mark.organization_id)
                self.session.execute(
                    text(
                        """
                        INSERT INTO artifact_gc_marks(
                            id, organization_id, bucket, object_key, checksum_sha256,
                            marked_at, not_before, state, completed_at, reason
                        ) VALUES (
                            :id, :organization_id, :bucket, :object_key, :checksum,
                            :marked_at, :not_before, :state, :completed_at, :reason
                        ) ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "id": mark.id,
                        "organization_id": mark.organization_id,
                        "bucket": mark.bucket,
                        "object_key": mark.storage_key,
                        "checksum": mark.checksum_sha256,
                        "marked_at": mark.marked_at,
                        "not_before": mark.not_before,
                        "state": mark.state.value,
                        "completed_at": mark.completed_at,
                        "reason": mark.reason,
                    },
                )

    def pending_gc_marks(self, organization_id: UUID) -> tuple[GcMark, ...]:
        self._assert_org(organization_id)
        rows = self.session.execute(
            text(
                """
                SELECT * FROM artifact_gc_marks
                WHERE organization_id=:organization_id AND state='MARKED'
                ORDER BY not_before, bucket, object_key
                """
            ),
            {"organization_id": self.organization_id},
        ).mappings().all()
        return tuple(self._gc_mark(row) for row in rows)

    def complete_gc_mark(self, mark: GcMark, audit: GcAudit) -> None:
        self._assert_org(mark.organization_id)
        self._assert_org(audit.organization_id)
        with self._transaction():
            result = self.session.execute(
                text(
                    """
                    UPDATE artifact_gc_marks
                    SET state=:state, completed_at=:completed_at, reason=:reason
                    WHERE id=:id AND organization_id=:organization_id AND state='MARKED'
                    """
                ),
                {
                    "state": mark.state.value,
                    "completed_at": mark.completed_at,
                    "reason": mark.reason,
                    "id": mark.id,
                    "organization_id": self.organization_id,
                },
            )
            if result.rowcount != 1:
                raise ArtifactHeadConflict(f"GC mark {mark.id} is no longer pending")
            self.session.execute(
                text(
                    """
                    INSERT INTO artifact_gc_audits(
                        id, organization_id, gc_mark_id, action, occurred_at,
                        bucket, object_key, checksum_sha256, detail
                    ) VALUES (
                        :id, :organization_id, :gc_mark_id, :action, :occurred_at,
                        :bucket, :object_key, :checksum, :detail
                    )
                    """
                ),
                {
                    "id": audit.id,
                    "organization_id": audit.organization_id,
                    "gc_mark_id": audit.gc_mark_id,
                    "action": audit.action,
                    "occurred_at": audit.occurred_at,
                    "bucket": audit.bucket,
                    "object_key": audit.storage_key,
                    "checksum": audit.checksum_sha256,
                    "detail": audit.detail,
                },
            )

    def protected_storage_locations(self, organization_id: UUID) -> frozenset[tuple[str, str]]:
        self._assert_org(organization_id)
        rows = self.session.execute(
            text(
                """
                SELECT DISTINCT bucket, object_key
                FROM artifact_files
                WHERE organization_id=:organization_id
                """
            ),
            {"organization_id": self.organization_id},
        ).all()
        return frozenset((row[0], row[1]) for row in rows)

    def _insert_artifact(self, artifact: Artifact, created_at: datetime) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO artifacts(
                    id, organization_id, project_id, kind, name, design_document_id,
                    rights_json, archived_at, retention_until, legal_hold,
                    created_at, updated_at, version
                ) VALUES (
                    :id, :organization_id, :project_id, :kind, :name,
                    :design_document_id, CAST(:rights_json AS jsonb), :archived_at,
                    :retention_until, :legal_hold, :created_at, :created_at, 1
                )
                """
            ),
            {
                "id": artifact.id,
                "organization_id": artifact.organization_id,
                "project_id": artifact.project_id,
                "kind": artifact.type.value,
                "name": artifact.name,
                "design_document_id": artifact.design_document_id,
                "rights_json": _json(artifact.rights),
                "archived_at": artifact.archived_at,
                "retention_until": artifact.retention_until,
                "legal_hold": artifact.legal_hold,
                "created_at": created_at,
            },
        )

    def _insert_version_record(
        self,
        version: ArtifactVersion,
        completeness: ProvenanceCompleteness,
    ) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO artifact_versions(
                    id, organization_id, artifact_id, branch_id, parent_version_id,
                    version_number, status, content_hash, primary_file_id,
                    design_document_version_id, constraint_snapshot_hash, rights_json,
                    quality_score, provenance_status, provenance_score,
                    created_by_type, created_by_id, created_at, metadata_json,
                    quality_summary_json
                ) VALUES (
                    :id, :organization_id, :artifact_id, :branch_id, :parent_version_id,
                    :version_number, :status, :content_hash, NULL,
                    :design_document_version_id, :constraint_snapshot_hash,
                    CAST(:rights_json AS jsonb), :quality_score, :provenance_status,
                    :provenance_score, :created_by_type, :created_by_id, :created_at,
                    '{}'::jsonb, '{}'::jsonb
                )
                """
            ),
            {
                "id": version.id,
                "organization_id": version.organization_id,
                "artifact_id": version.artifact_id,
                "branch_id": version.branch_id,
                "parent_version_id": version.parent_version_id,
                "version_number": version.version_number,
                "status": _db_status(version.status),
                "content_hash": version.content_hash,
                "design_document_version_id": version.design_document_version_id,
                "constraint_snapshot_hash": version.constraint_snapshot_hash,
                "rights_json": _json(version.rights),
                "quality_score": version.quality_score,
                "provenance_status": completeness.status.value,
                "provenance_score": float(completeness.score),
                "created_by_type": _db_creator(version.created_by_type),
                "created_by_id": version.created_by_id,
                "created_at": version.created_at,
            },
        )

    def _insert_branch(self, branch: ArtifactBranch, project_id: UUID) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO artifact_branches(
                    id, organization_id, project_id, artifact_id, name,
                    base_version_id, head_version_id, created_by_type,
                    created_by_id, created_at, updated_at, version
                ) VALUES (
                    :id, :organization_id, :project_id, :artifact_id, :name,
                    :base_version_id, :head_version_id, :created_by_type,
                    :created_by_id, :created_at, :created_at, 1
                )
                """
            ),
            {
                "id": branch.id,
                "organization_id": branch.organization_id,
                "project_id": project_id,
                "artifact_id": branch.artifact_id,
                "name": branch.name,
                "base_version_id": branch.base_version_id,
                "head_version_id": branch.head_version_id,
                "created_by_type": _db_creator(branch.created_by_type),
                "created_by_id": branch.created_by_id,
                "created_at": branch.created_at,
            },
        )

    def _insert_file(self, version: ArtifactVersion, item: ArtifactFile) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO artifact_files(
                    id, organization_id, artifact_version_id, role, bucket,
                    object_key, checksum_sha256, mime_type, byte_size, width,
                    height, duration_ms, metadata_json, created_at
                ) VALUES (
                    :id, :organization_id, :artifact_version_id, :role, :bucket,
                    :object_key, :checksum, :mime_type, :byte_size, :width,
                    :height, :duration_ms, CAST(:metadata_json AS jsonb), :created_at
                )
                """
            ),
            {
                "id": item.id,
                "organization_id": version.organization_id,
                "artifact_version_id": version.id,
                "role": item.role.value,
                "bucket": item.bucket,
                "object_key": item.storage_key,
                "checksum": item.checksum_sha256,
                "mime_type": item.mime_type,
                "byte_size": item.size_bytes,
                "width": item.width,
                "height": item.height,
                "duration_ms": item.duration_ms,
                "metadata_json": _json(dict(item.metadata)),
                "created_at": version.created_at,
            },
        )

    def _insert_edge(self, edge: LineageEdge) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO artifact_edges(
                    id, organization_id, from_artifact_version_id,
                    to_artifact_version_id, edge_type, metadata_json, created_at
                ) VALUES (
                    :id, :organization_id, :source_id, :version_id,
                    :edge_type, CAST(:metadata_json AS jsonb), :created_at
                )
                """
            ),
            {
                "id": edge.id,
                "organization_id": edge.organization_id,
                "source_id": edge.source_artifact_version_id,
                "version_id": edge.artifact_version_id,
                "edge_type": edge.type.value,
                "metadata_json": _json(dict(edge.metadata)),
                "created_at": edge.created_at,
            },
        )

    def _insert_provenance(
        self,
        version_id: UUID,
        envelope: ProvenanceEnvelope,
        completeness: ProvenanceCompleteness,
    ) -> None:
        record = envelope.record
        payload = _json(record)
        self.session.execute(
            text(
                """
                INSERT INTO artifact_provenance(
                    id, organization_id, artifact_version_id, provenance_json,
                    content_hash, agent_run_id, task_id, generation_id, provider,
                    model, provider_request_id, prompt_hash, prompt_template_version,
                    recipe_version, compiler_version, agent_version, code_git_sha,
                    constraint_snapshot_hash, completeness_status, completeness_score,
                    missing_fields_json, created_at
                ) VALUES (
                    :id, :organization_id, :artifact_version_id,
                    CAST(:provenance_json AS jsonb), :content_hash, :agent_run_id,
                    :task_id, :generation_id, :provider, :model, :provider_request_id,
                    :prompt_hash, :prompt_template_version, :recipe_version,
                    :compiler_version, :agent_version, :code_git_sha,
                    :constraint_snapshot_hash, :completeness_status,
                    :completeness_score, CAST(:missing_fields_json AS jsonb), now()
                )
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": self.organization_id,
                "artifact_version_id": version_id,
                "provenance_json": payload,
                "content_hash": _provenance_hash(envelope),
                "agent_run_id": record.agent_run_id,
                "task_id": record.task_id,
                "generation_id": record.generation_id,
                "provider": record.provider,
                "model": record.model,
                "provider_request_id": record.provider_request_id,
                "prompt_hash": record.prompt_hash,
                "prompt_template_version": record.prompt_template_version,
                "recipe_version": record.recipe_version,
                "compiler_version": envelope.compiler_version,
                "agent_version": envelope.agent_version,
                "code_git_sha": record.code_git_sha,
                "constraint_snapshot_hash": record.constraint_snapshot_hash,
                "completeness_status": completeness.status.value,
                "completeness_score": float(completeness.score),
                "missing_fields_json": _json(list(completeness.missing_fields)),
            },
        )

    def _insert_approval(self, approval: ApprovalRecord) -> None:
        self._assert_org(approval.organization_id)
        self.session.execute(
            text(
                """
                INSERT INTO artifact_version_approvals(
                    id, organization_id, artifact_version_id, approved_by_id,
                    approved_at, validation_ref
                ) VALUES (
                    :id, :organization_id, :artifact_version_id, :approved_by_id,
                    :approved_at, :validation_ref
                )
                """
            ),
            approval.model_dump(),
        )

    def _insert_outbox(self, event: ArtifactOutboxEvent) -> None:
        self._assert_org(event.organization_id)
        self.session.execute(
            text(
                """
                INSERT INTO artifact_outbox_events(
                    id, organization_id, event_type, aggregate_id,
                    aggregate_version_id, occurred_at, payload_json
                ) VALUES (
                    :id, :organization_id, :event_type, :aggregate_id,
                    :aggregate_version_id, :occurred_at, CAST(:payload_json AS jsonb)
                )
                """
            ),
            {
                "id": event.id,
                "organization_id": event.organization_id,
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
                "aggregate_version_id": event.aggregate_version_id,
                "occurred_at": event.occurred_at,
                "payload_json": _json(event.payload),
            },
        )

    def _files(self, version_id: UUID) -> tuple[ArtifactFile, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT id, role, bucket, object_key, mime_type, byte_size,
                       checksum_sha256, width, height, duration_ms, metadata_json
                FROM artifact_files
                WHERE artifact_version_id=:version_id AND organization_id=:organization_id
                ORDER BY created_at, id
                """
            ),
            {"version_id": version_id, "organization_id": self.organization_id},
        ).mappings().all()
        return tuple(
            ArtifactFile(
                id=row["id"],
                role=FileRole(row["role"]),
                bucket=row["bucket"],
                storage_key=row["object_key"],
                mime_type=row["mime_type"],
                size_bytes=row["byte_size"],
                checksum_sha256=row["checksum_sha256"],
                width=row["width"],
                height=row["height"],
                duration_ms=row["duration_ms"],
                metadata=_metadata_tuple(row["metadata_json"]),
            )
            for row in rows
        )

    @staticmethod
    def _branch(row: Mapping[str, Any]) -> ArtifactBranch:
        return ArtifactBranch(
            id=row["id"],
            organization_id=row["organization_id"],
            artifact_id=row["artifact_id"],
            name=row["name"],
            base_version_id=row["base_version_id"],
            head_version_id=row["head_version_id"],
            created_by_type=_model_creator(row["created_by_type"]),
            created_by_id=row["created_by_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _version(
        row: Mapping[str, Any], files: tuple[ArtifactFile, ...]
    ) -> ArtifactVersion:
        quality = row["quality_score"]
        if isinstance(quality, Decimal):
            quality = float(quality)
        return ArtifactVersion(
            id=row["id"],
            organization_id=row["organization_id"],
            artifact_id=row["artifact_id"],
            branch_id=row["branch_id"],
            parent_version_id=row["parent_version_id"],
            version_number=row["version_number"],
            status=_model_status(row["status"]),
            content_hash=row["content_hash"],
            primary_file_id=row["primary_file_id"],
            design_document_version_id=row["design_document_version_id"],
            quality_score=quality,
            constraint_snapshot_hash=row["constraint_snapshot_hash"],
            created_by_type=_model_creator(row["created_by_type"]),
            created_by_id=row["created_by_id"],
            created_at=row["created_at"],
            files=files,
            provenance=(
                ProvenanceRecord.model_validate(row["provenance_json"])
                if row["provenance_json"] is not None
                else ProvenanceRecord(code_git_sha="0" * 40)
            ),
            rights=RightsPolicy.model_validate(row["rights_json"]),
        )

    @staticmethod
    def _gc_mark(row: Mapping[str, Any]) -> GcMark:
        return GcMark(
            id=row["id"],
            organization_id=row["organization_id"],
            bucket=row["bucket"],
            storage_key=row["object_key"],
            checksum_sha256=row["checksum_sha256"],
            marked_at=row["marked_at"],
            not_before=row["not_before"],
            state=GcMarkState(row["state"]),
            completed_at=row["completed_at"],
            reason=row["reason"],
        )

    def _assert_org(self, organization_id: UUID) -> None:
        if organization_id != self.organization_id:
            raise ArtifactNotFound("resource not found in organization scope")
