from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .contracts import IdentityReferenceSet, IdentityValidationResult, CalibrationReport
from .repository import IdentityNotFound


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PostgresIdentityRepository:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def reserve_version(self, organization_id: UUID, identity_id: UUID) -> int:
        if organization_id != self.organization_id:
            raise IdentityNotFound(str(identity_id))
        with self._transaction():
            row = self.session.execute(
                text("""
                    INSERT INTO identity_version_counters
                    (identity_id, organization_id, next_version)
                    VALUES (:identity_id, :organization_id, 2)
                    ON CONFLICT (identity_id) DO UPDATE
                    SET next_version = identity_version_counters.next_version + 1
                    WHERE identity_version_counters.organization_id = EXCLUDED.organization_id
                    RETURNING next_version - 1 AS allocated_version
                """),
                {
                    "organization_id": organization_id,
                    "identity_id": identity_id,
                },
            ).mappings().one_or_none()
            if row is None:
                raise IdentityNotFound(str(identity_id))
            return int(row["allocated_version"])

    def save_reference_set(self, value: IdentityReferenceSet) -> None:
        with self._transaction():
            self.session.execute(
                text("""
                    INSERT INTO identity_reference_sets
                    (id, organization_id, project_id, brand_id, identity_type, name,
                     created_by, privacy_authorized, created_at)
                    VALUES (:id, :organization_id, :project_id, :brand_id, :identity_type,
                            :name, :created_by, :privacy_authorized, :created_at)
                    ON CONFLICT (id) DO UPDATE
                    SET name = identity_reference_sets.name
                    WHERE identity_reference_sets.organization_id = EXCLUDED.organization_id
                    RETURNING organization_id
                """),
                {
                    "id": value.id,
                    "organization_id": value.organization_id,
                    "project_id": value.project_id,
                    "brand_id": value.brand_id,
                    "identity_type": value.identity_type.value,
                    "name": value.name,
                    "created_by": value.created_by,
                    "privacy_authorized": value.privacy_authorized,
                    "created_at": value.created_at,
                },
            )
            root = self.session.execute(
                text("""
                    SELECT organization_id, project_id, brand_id, identity_type,
                           privacy_authorized
                    FROM identity_reference_sets
                    WHERE id=:identity_id
                """),
                {"identity_id": value.id},
            ).mappings().one()
            if root["organization_id"] != self.organization_id:
                raise IdentityNotFound(str(value.id))
            expected_scope = (
                value.project_id,
                value.brand_id,
                value.identity_type.value,
                value.privacy_authorized,
            )
            persisted_scope = (
                root["project_id"],
                root["brand_id"],
                str(root["identity_type"]),
                bool(root["privacy_authorized"]),
            )
            if persisted_scope != expected_scope:
                raise ValueError("IDENTITY_REFERENCE_SCOPE_IMMUTABLE")
            self.session.execute(
                text("""
                    INSERT INTO identity_reference_set_versions
                    (id, organization_id, identity_id, version_number, snapshot_hash,
                     canonical_asset_ids_json, reference_views_json, threshold_profile_json,
                     notes, created_at)
                    VALUES (gen_random_uuid(), :organization_id, :identity_id, :version_number,
                            :snapshot_hash, CAST(:assets AS jsonb), CAST(:views AS jsonb),
                            CAST(:profile AS jsonb), :notes, :created_at)
                """),
                {
                    "organization_id": value.organization_id,
                    "identity_id": value.id,
                    "version_number": value.version,
                    "snapshot_hash": value.snapshot_hash,
                    "assets": _json([str(v) for v in value.canonical_asset_ids]),
                    "views": _json(value.reference_views),
                    "profile": _json(value.threshold_profile),
                    "notes": value.notes,
                    "created_at": value.created_at,
                },
            )

    def get_latest(self, organization_id: UUID, identity_id: UUID) -> IdentityReferenceSet:
        if organization_id != self.organization_id:
            raise IdentityNotFound(str(identity_id))
        row: Mapping[str, Any] | None = self.session.execute(
            text("""
                SELECT s.*, v.version_number, v.snapshot_hash, v.canonical_asset_ids_json,
                       v.reference_views_json, v.threshold_profile_json, v.notes,
                       v.created_at AS version_created_at
                FROM identity_reference_sets s
                JOIN LATERAL (
                    SELECT * FROM identity_reference_set_versions
                    WHERE identity_id=s.id AND organization_id=s.organization_id
                    ORDER BY version_number DESC LIMIT 1
                ) v ON TRUE
                WHERE s.id=:identity_id AND s.organization_id=:organization_id
            """),
            {"identity_id": identity_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise IdentityNotFound(str(identity_id))
        return IdentityReferenceSet.model_validate({
            "id": row["id"],
            "organization_id": row["organization_id"],
            "project_id": row["project_id"],
            "brand_id": row["brand_id"],
            "identity_type": row["identity_type"],
            "name": row["name"],
            "canonical_asset_ids": row["canonical_asset_ids_json"],
            "reference_views": row["reference_views_json"],
            "notes": row["notes"],
            "threshold_profile": row["threshold_profile_json"],
            "version": row["version_number"],
            "snapshot_hash": row["snapshot_hash"],
            "created_at": row["version_created_at"],
            "created_by": row["created_by"],
            "privacy_authorized": row["privacy_authorized"],
        })

    def save_validation(self, value: object) -> None:
        if not isinstance(value, IdentityValidationResult):
            return
        with self._transaction():
            version_id = self.session.execute(
                text("""
                    SELECT id FROM identity_reference_set_versions
                    WHERE organization_id=:organization_id AND identity_id=:identity_id
                      AND version_number=:version_number
                """),
                {
                    "organization_id": self.organization_id,
                    "identity_id": value.identity_id,
                    "version_number": value.reference_version,
                },
            ).scalar_one()
            self.session.execute(
                text("""
                    INSERT INTO identity_validation_records
                    (id, organization_id, identity_version_id, candidate_asset_id, node_id,
                     status, identity_score, confidence, threshold_profile_json,
                     signal_scores_json, region_json,
                     evidence_refs_json, failure_codes_json, provider_version, created_at)
                    VALUES (gen_random_uuid(), :organization_id, :identity_version_id,
                            :candidate_asset_id, :node_id, :status, :identity_score,
                            :confidence, CAST(:profile AS jsonb),
                            CAST(:signals AS jsonb), CAST(:region AS jsonb),
                            CAST(:evidence AS jsonb),
                            CAST(:failures AS jsonb), :provider_version, now())
                """),
                {
                    "organization_id": self.organization_id,
                    "identity_version_id": version_id,
                    "candidate_asset_id": value.candidate_asset_id,
                    "node_id": value.candidate_node_id,
                    "status": value.status.value,
                    "identity_score": value.identity_score,
                    "confidence": value.confidence,
                    "profile": _json(value.threshold_profile),
                    "signals": _json(value.signal_scores),
                    "region": _json(value.region) if value.region else None,
                    "evidence": _json(value.evidence_refs),
                    "failures": _json(value.failure_codes),
                    "provider_version": value.provider_version,
                },
            )

    def save_calibration(self, value: object) -> None:
        if not isinstance(value, CalibrationReport):
            return
        if value.organization_id != self.organization_id:
            raise PermissionError("IDENTITY_CALIBRATION_TENANT_MISMATCH")
        with self._transaction():
            self.session.execute(
                text("""
                    INSERT INTO identity_calibration_reports
                    (id, organization_id, identity_type, profile_key, version_number, dataset_hash,
                     selected_threshold, target_precision, metrics_json, sample_count, created_at)
                    VALUES (:id, :organization_id, :identity_type, :profile_key, :version_number,
                            :dataset_hash, :selected_threshold, :target_precision,
                            CAST(:metrics AS jsonb), :sample_count, :created_at)
                """),
                {
                    "id": value.id,
                    "organization_id": value.organization_id,
                    "identity_type": value.identity_type.value,
                    "profile_key": value.profile_key,
                    "version_number": value.version,
                    "dataset_hash": value.dataset_hash,
                    "selected_threshold": value.selected_threshold,
                    "target_precision": value.target_precision,
                    "metrics": _json(value.metrics),
                    "sample_count": value.sample_count,
                    "created_at": value.created_at,
                },
            )
