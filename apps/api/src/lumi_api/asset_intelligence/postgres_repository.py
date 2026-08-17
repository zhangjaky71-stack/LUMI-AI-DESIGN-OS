from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_asset_intelligence import (
    AccessScope,
    AssetAnalysisRecord,
    AssetIndexVersion,
    AssetIntelligenceNotFound,
    AssetRegion,
    BoundingBox,
    MetadataField,
    OcrSpan,
    SearchFilters,
    UsageSignal,
)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), default=str)


def _vector(value: tuple[float, ...]) -> str:
    return "[" + ",".join(format(item, ".17g") for item in value) + "]"


def _parse_vector(value: Any) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(float(item) for item in value)
    raw = str(value).strip().strip("[]")
    if not raw:
        return ()
    return tuple(float(item) for item in raw.split(","))


class PostgresAssetIntelligenceRepository:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def _assert_org(self, organization_id: UUID) -> None:
        if organization_id != self.organization_id:
            raise AssetIntelligenceNotFound("TENANT_RESOURCE_NOT_FOUND")

    @staticmethod
    def _index(row: Any) -> AssetIndexVersion:
        return AssetIndexVersion(
            id=row["id"],
            organization_id=row["organization_id"],
            version=row["version_number"],
            analyzer_version=row["analyzer_version"],
            embedding_model_key=row["embedding_model_key"],
            embedding_revision_key=row["embedding_revision_key"],
            embedding_version=row["embedding_version"],
            embedding_dimensions=row["embedding_dimensions"],
            embedding_space_id=row["embedding_space_id"],
            registry_version_id=row["registry_version_id"],
            state=row["state"],
            created_at=row["created_at"],
            activated_at=row["activated_at"],
            coverage_count=row["coverage_count"],
        )

    @staticmethod
    def _analysis(row: Any) -> AssetAnalysisRecord:
        metadata = {
            key: MetadataField(**value)
            for key, value in (row["metadata_json"] or {}).items()
        }
        ocr = tuple(
            OcrSpan(
                text=value["text"],
                confidence=float(value["confidence"]),
                bbox=BoundingBox(**value["bbox"]),
                analyzer_id=value["analyzer_id"],
                analyzer_version=value["analyzer_version"],
                language=value.get("language"),
            )
            for value in (row["ocr_spans_json"] or [])
        )
        regions = tuple(
            AssetRegion(
                region_id=value["region_id"],
                label=value["label"],
                confidence=float(value["confidence"]),
                bbox=BoundingBox(**value["bbox"]),
                analyzer_id=value["analyzer_id"],
                analyzer_version=value["analyzer_version"],
            )
            for value in (row["regions_json"] or [])
        )
        return AssetAnalysisRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            asset_id=row["asset_id"],
            asset_version=row["asset_version"],
            project_id=row["project_id"],
            brand_id=row["brand_id"],
            index_id=row["index_id"],
            index_version=row["index_version"],
            state=row["state"],
            checksum_sha256=row["checksum_sha256"],
            source=row["source"],
            mime_type=row["mime_type"],
            media_kind=row["media_kind"],
            rights_level=row["rights_level"],
            commercial_use=bool(row["commercial_use"]),
            training_authorized=bool(row["training_authorized"]),
            permission_tags=tuple(row["permission_tags_json"] or ()),
            preview_ref=row["preview_ref"],
            metadata=metadata,
            ocr_spans=ocr,
            regions=regions,
            semantic_description=row["semantic_description"],
            visual_tags=tuple(row["visual_tags_json"] or ()),
            embedding=_parse_vector(row.get("embedding_text")),
            embedding_id=row["embedding_id"],
            perceptual_hash=row["perceptual_hash"],
            language=row["language"],
            local_signature=tuple(row["local_signature_json"] or ()),
            color_signature=tuple(row["color_signature_json"] or ()),
            brand_region_signature=tuple(row["brand_region_signature_json"] or ()),
            analyzer_version=row["analyzer_version"],
            embedding_model_key=row["embedding_model_key"],
            embedding_revision_key=row["embedding_revision_key"],
            embedding_version=row["embedding_version"],
            registry_version_id=row["registry_version_id"],
            evidence_refs=tuple(row["evidence_refs_json"] or ()),
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
            error_code=row["error_code"],
        )

    def reserve_index_version(self, organization_id: UUID) -> int:
        self._assert_org(organization_id)
        with self._transaction():
            row = self.session.execute(
                text("""
                    INSERT INTO asset_intelligence_index_counters
                        (organization_id, next_version)
                    VALUES (:organization_id, 2)
                    ON CONFLICT (organization_id) DO UPDATE
                    SET next_version = asset_intelligence_index_counters.next_version + 1
                    RETURNING next_version - 1 AS reserved_version
                """),
                {"organization_id": organization_id},
            ).mappings().one()
            return int(row["reserved_version"])

    def create_index(self, value: AssetIndexVersion) -> None:
        self._assert_org(value.organization_id)
        with self._transaction():
            self.session.execute(
                text("""
                    INSERT INTO asset_intelligence_indexes
                    (id, organization_id, version_number, analyzer_version,
                     embedding_model_key, embedding_revision_key, embedding_version,
                     embedding_dimensions, embedding_space_id, registry_version_id,
                     state, coverage_count, created_at, activated_at)
                    VALUES (:id, :organization_id, :version_number, :analyzer_version,
                            :embedding_model_key, :embedding_revision_key, :embedding_version,
                            :embedding_dimensions, :embedding_space_id, :registry_version_id,
                            :state, :coverage_count, :created_at, :activated_at)
                """),
                {
                    "id": value.id,
                    "organization_id": value.organization_id,
                    "version_number": value.version,
                    "analyzer_version": value.analyzer_version,
                    "embedding_model_key": value.embedding_model_key,
                    "embedding_revision_key": value.embedding_revision_key,
                    "embedding_version": value.embedding_version,
                    "embedding_dimensions": value.embedding_dimensions,
                    "embedding_space_id": value.embedding_space_id,
                    "registry_version_id": value.registry_version_id,
                    "state": value.state,
                    "coverage_count": value.coverage_count,
                    "created_at": value.created_at,
                    "activated_at": value.activated_at,
                },
            )

    def get_index(self, organization_id: UUID, index_id: UUID) -> AssetIndexVersion:
        self._assert_org(organization_id)
        row = self.session.execute(
            text("""
                SELECT * FROM asset_intelligence_indexes
                WHERE id=:index_id AND organization_id=:organization_id
            """),
            {"index_id": index_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise AssetIntelligenceNotFound(str(index_id))
        return self._index(row)

    def active_index(self, organization_id: UUID) -> AssetIndexVersion:
        self._assert_org(organization_id)
        row = self.session.execute(
            text("""
                SELECT * FROM asset_intelligence_indexes
                WHERE organization_id=:organization_id AND state='ACTIVE'
                ORDER BY version_number DESC LIMIT 1
            """),
            {"organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise AssetIntelligenceNotFound("ACTIVE_INDEX_NOT_FOUND")
        return self._index(row)

    def mark_index_ready(
        self,
        organization_id: UUID,
        index_id: UUID,
        coverage_count: int,
    ) -> AssetIndexVersion:
        self._assert_org(organization_id)
        with self._transaction():
            row = self.session.execute(
                text("""
                    UPDATE asset_intelligence_indexes
                    SET state='READY', coverage_count=:coverage_count
                    WHERE id=:index_id AND organization_id=:organization_id
                      AND state='BUILDING'
                    RETURNING *
                """),
                {
                    "index_id": index_id,
                    "organization_id": organization_id,
                    "coverage_count": coverage_count,
                },
            ).mappings().one_or_none()
            if row is None:
                raise ValueError("ASSET_INDEX_NOT_BUILDING")
            return self._index(row)

    def activate_index(
        self,
        organization_id: UUID,
        index_id: UUID,
        activated_at: datetime,
        expected_active_index_id: UUID | None,
    ) -> AssetIndexVersion:
        self._assert_org(organization_id)
        with self._transaction():
            self.session.execute(
                text("SELECT id FROM organizations WHERE id=:organization_id FOR UPDATE"),
                {"organization_id": organization_id},
            ).one()
            candidate = self.session.execute(
                text("""
                    SELECT * FROM asset_intelligence_indexes
                    WHERE id=:index_id AND organization_id=:organization_id
                    FOR UPDATE
                """),
                {"index_id": index_id, "organization_id": organization_id},
            ).mappings().one_or_none()
            if candidate is None:
                raise AssetIntelligenceNotFound(str(index_id))
            if candidate["state"] != "READY":
                raise ValueError("ASSET_INDEX_NOT_READY")
            current_active = self.session.execute(
                text("""
                    SELECT id FROM asset_intelligence_indexes
                    WHERE organization_id=:organization_id AND state='ACTIVE'
                    ORDER BY version_number DESC LIMIT 1
                    FOR UPDATE
                """),
                {"organization_id": organization_id},
            ).scalar_one_or_none()
            if current_active != expected_active_index_id:
                raise ValueError("ASSET_INDEX_ACTIVE_HEAD_CONFLICT")
            self.session.execute(
                text("""
                    UPDATE asset_intelligence_indexes SET state='RETIRED'
                    WHERE organization_id=:organization_id AND state='ACTIVE'
                """),
                {"organization_id": organization_id},
            )
            row = self.session.execute(
                text("""
                    UPDATE asset_intelligence_indexes
                    SET state='ACTIVE', activated_at=:activated_at
                    WHERE id=:index_id AND organization_id=:organization_id
                    RETURNING *
                """),
                {
                    "index_id": index_id,
                    "organization_id": organization_id,
                    "activated_at": activated_at,
                },
            ).mappings().one()
            return self._index(row)

    def upsert_analysis(self, value: AssetAnalysisRecord) -> None:
        self._assert_org(value.organization_id)
        with self._transaction():
            embedding_id = None
            if value.embedding is not None:
                self.session.execute(
                    text("""
                        INSERT INTO asset_embeddings
                        (id, organization_id, asset_id, embedding_model, embedding_version,
                         dimensions, content_hash, embedding, created_at)
                        VALUES (gen_random_uuid(), :organization_id, :asset_id,
                                :embedding_model, :embedding_version, :dimensions,
                                :content_hash, CAST(:embedding AS vector), now())
                        ON CONFLICT (asset_id, embedding_model, embedding_version, content_hash)
                        DO NOTHING
                    """),
                    {
                        "organization_id": value.organization_id,
                        "asset_id": value.asset_id,
                        "embedding_model": value.embedding_model_key,
                        "embedding_version": value.embedding_version,
                        "dimensions": len(value.embedding),
                        "content_hash": value.asset_version,
                        "embedding": _vector(value.embedding),
                    },
                )
                embedding_id = self.session.execute(
                    text("""
                        SELECT id FROM asset_embeddings
                        WHERE organization_id=:organization_id AND asset_id=:asset_id
                          AND embedding_model=:embedding_model
                          AND embedding_version=:embedding_version
                          AND content_hash=:content_hash
                    """),
                    {
                        "organization_id": value.organization_id,
                        "asset_id": value.asset_id,
                        "embedding_model": value.embedding_model_key,
                        "embedding_version": value.embedding_version,
                        "content_hash": value.asset_version,
                    },
                ).scalar_one()
            self.session.execute(
                text("""
                    INSERT INTO asset_intelligence_analysis
                    (id, organization_id, asset_id, asset_version, project_id, brand_id,
                     index_id, index_version, state, checksum_sha256, source, mime_type,
                     media_kind, rights_level, commercial_use, training_authorized,
                     permission_tags_json, preview_ref, metadata_json, ocr_spans_json,
                     regions_json, semantic_description, visual_tags_json, embedding_id,
                     perceptual_hash, language, local_signature_json, color_signature_json,
                     brand_region_signature_json, analyzer_version, embedding_model_key,
                     embedding_revision_key, embedding_version, registry_version_id,
                     evidence_refs_json, created_at, deleted_at, error_code)
                    VALUES (:id, :organization_id, :asset_id, :asset_version, :project_id,
                            :brand_id, :index_id, :index_version, :state, :checksum_sha256,
                            :source, :mime_type, :media_kind, :rights_level, :commercial_use,
                            :training_authorized, CAST(:permission_tags AS jsonb), :preview_ref,
                            CAST(:metadata AS jsonb), CAST(:ocr AS jsonb), CAST(:regions AS jsonb),
                            :semantic_description, CAST(:tags AS jsonb), :embedding_id,
                            :perceptual_hash, :language, CAST(:local_signature AS jsonb),
                            CAST(:color_signature AS jsonb), CAST(:brand_signature AS jsonb),
                            :analyzer_version, :embedding_model_key, :embedding_revision_key,
                            :embedding_version, :registry_version_id, CAST(:evidence AS jsonb),
                            :created_at, :deleted_at, :error_code)
                    ON CONFLICT (organization_id, asset_id, index_id) DO UPDATE SET
                        id=EXCLUDED.id, asset_version=EXCLUDED.asset_version,
                        project_id=EXCLUDED.project_id, brand_id=EXCLUDED.brand_id,
                        state=EXCLUDED.state, checksum_sha256=EXCLUDED.checksum_sha256,
                        rights_level=EXCLUDED.rights_level,
                        commercial_use=EXCLUDED.commercial_use,
                        training_authorized=EXCLUDED.training_authorized,
                        permission_tags_json=EXCLUDED.permission_tags_json,
                        preview_ref=EXCLUDED.preview_ref, metadata_json=EXCLUDED.metadata_json,
                        ocr_spans_json=EXCLUDED.ocr_spans_json, regions_json=EXCLUDED.regions_json,
                        semantic_description=EXCLUDED.semantic_description,
                        visual_tags_json=EXCLUDED.visual_tags_json,
                        embedding_id=EXCLUDED.embedding_id,
                        perceptual_hash=EXCLUDED.perceptual_hash, language=EXCLUDED.language,
                        local_signature_json=EXCLUDED.local_signature_json,
                        color_signature_json=EXCLUDED.color_signature_json,
                        brand_region_signature_json=EXCLUDED.brand_region_signature_json,
                        evidence_refs_json=EXCLUDED.evidence_refs_json,
                        created_at=EXCLUDED.created_at, deleted_at=EXCLUDED.deleted_at,
                        error_code=EXCLUDED.error_code
                """),
                {
                    "id": value.id,
                    "organization_id": value.organization_id,
                    "asset_id": value.asset_id,
                    "asset_version": value.asset_version,
                    "project_id": value.project_id,
                    "brand_id": value.brand_id,
                    "index_id": value.index_id,
                    "index_version": value.index_version,
                    "state": value.state,
                    "checksum_sha256": value.checksum_sha256,
                    "source": value.source,
                    "mime_type": value.mime_type,
                    "media_kind": value.media_kind,
                    "rights_level": value.rights_level,
                    "commercial_use": value.commercial_use,
                    "training_authorized": value.training_authorized,
                    "permission_tags": _json(value.permission_tags),
                    "preview_ref": value.preview_ref,
                    "metadata": _json(value.metadata),
                    "ocr": _json(value.ocr_spans),
                    "regions": _json(value.regions),
                    "semantic_description": value.semantic_description,
                    "tags": _json(value.visual_tags),
                    "embedding_id": embedding_id,
                    "perceptual_hash": value.perceptual_hash,
                    "language": value.language,
                    "local_signature": _json(value.local_signature),
                    "color_signature": _json(value.color_signature),
                    "brand_signature": _json(value.brand_region_signature),
                    "analyzer_version": value.analyzer_version,
                    "embedding_model_key": value.embedding_model_key,
                    "embedding_revision_key": value.embedding_revision_key,
                    "embedding_version": value.embedding_version,
                    "registry_version_id": value.registry_version_id,
                    "evidence": _json(value.evidence_refs),
                    "created_at": value.created_at,
                    "deleted_at": value.deleted_at,
                    "error_code": value.error_code,
                },
            )

    def _analysis_select(self) -> str:
        return """
            SELECT a.*, e.embedding::text AS embedding_text
            FROM asset_intelligence_analysis a
            LEFT JOIN asset_embeddings e
              ON e.id=a.embedding_id AND e.organization_id=a.organization_id
        """

    def get_analysis(
        self,
        organization_id: UUID,
        asset_id: UUID,
        index_id: UUID,
    ) -> AssetAnalysisRecord | None:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(self._analysis_select() + """
                WHERE a.organization_id=:organization_id
                  AND a.asset_id=:asset_id AND a.index_id=:index_id
            """),
            {
                "organization_id": organization_id,
                "asset_id": asset_id,
                "index_id": index_id,
            },
        ).mappings().one_or_none()
        return self._analysis(row) if row else None

    def scoped_candidates(
        self,
        scope: AccessScope,
        filters: SearchFilters,
        index_id: UUID,
    ) -> tuple[AssetAnalysisRecord, ...]:
        self._assert_org(scope.organization_id)
        # Scope and rights predicates are inside SQL before rows reach application scoring.
        rows = self.session.execute(
            text(self._analysis_select() + """
                JOIN assets live_asset
                  ON live_asset.id=a.asset_id
                 AND live_asset.organization_id=a.organization_id
                LEFT JOIN asset_rights live_rights
                  ON live_rights.asset_id=a.asset_id
                 AND live_rights.organization_id=a.organization_id
                WHERE a.organization_id=:organization_id AND a.index_id=:index_id
                  AND a.state='READY' AND a.deleted_at IS NULL
                  AND live_asset.status='ready' AND live_asset.deleted_at IS NULL
                  AND (:project_filter = false OR a.project_id = ANY(CAST(:project_ids AS uuid[])))
                  AND (:brand_filter = false OR a.brand_id = ANY(CAST(:brand_ids AS uuid[])))
                  AND COALESCE(live_rights.rights_level, 'unknown')
                      = ANY(CAST(:allowed_rights AS varchar[]))
                  AND (
                      :commercial_use = false
                      OR COALESCE(live_rights.commercial_use, false) = true
                  )
                  AND (:media_filter = false OR a.media_kind = ANY(CAST(:media_kinds AS varchar[])))
                  AND (
                      :rights_filter = false
                      OR COALESCE(live_rights.rights_level, 'unknown')
                         = ANY(CAST(:filter_rights AS varchar[]))
                  )
                  AND a.permission_tags_json <@ CAST(:permission_tags AS jsonb)
                  AND (:tag_filter = false OR a.visual_tags_json @> CAST(:tags AS jsonb))
                  AND (
                      :filter_project = false
                      OR a.project_id = ANY(CAST(:filter_project_ids AS uuid[]))
                  )
                  AND (:filter_brand = false OR a.brand_id = ANY(CAST(:filter_brand_ids AS uuid[])))
                  AND (:created_after IS NULL OR a.created_at >= :created_after)
                  AND (:created_before IS NULL OR a.created_at <= :created_before)
                ORDER BY a.asset_id, a.asset_version
            """),
            {
                "organization_id": scope.organization_id,
                "index_id": index_id,
                "project_filter": scope.project_ids is not None,
                "project_ids": list(scope.project_ids or ()),
                "brand_filter": scope.brand_ids is not None,
                "brand_ids": list(scope.brand_ids or ()),
                "allowed_rights": list(scope.allowed_rights),
                "commercial_use": scope.commercial_use,
                "media_filter": bool(filters.media_kinds),
                "media_kinds": list(filters.media_kinds),
                "rights_filter": bool(filters.rights),
                "filter_rights": list(filters.rights),
                "permission_tags": _json(scope.permission_tags),
                "tag_filter": bool(filters.tags),
                "tags": _json(filters.tags),
                "filter_project": bool(filters.project_ids),
                "filter_project_ids": list(filters.project_ids),
                "filter_brand": bool(filters.brand_ids),
                "filter_brand_ids": list(filters.brand_ids),
                "created_after": filters.created_after,
                "created_before": filters.created_before,
            },
        ).mappings().all()
        return tuple(self._analysis(row) for row in rows)

    def asset_ids_for_index(self, organization_id: UUID, index_id: UUID) -> set[UUID]:
        self._assert_org(organization_id)
        return set(self.session.execute(
            text("""
                SELECT asset_id FROM asset_intelligence_analysis
                WHERE organization_id=:organization_id AND index_id=:index_id
                  AND state='READY' AND deleted_at IS NULL
            """),
            {"organization_id": organization_id, "index_id": index_id},
        ).scalars().all())

    def add_usage_signal(self, signal: UsageSignal) -> None:
        self._assert_org(signal.organization_id)
        with self._transaction():
            self.session.execute(
                text("""
                    INSERT INTO asset_intelligence_usage_signals
                    (id, organization_id, asset_id, project_id, signal, actor_id,
                     training_authorization_granted, occurred_at)
                    VALUES (:id, :organization_id, :asset_id, :project_id, :signal,
                            :actor_id, :training_authorization_granted, :occurred_at)
                """),
                {
                    "id": signal.id,
                    "organization_id": signal.organization_id,
                    "asset_id": signal.asset_id,
                    "project_id": signal.project_id,
                    "signal": signal.signal,
                    "actor_id": signal.actor_id,
                    "training_authorization_granted": signal.training_authorization_granted,
                    "occurred_at": signal.occurred_at,
                },
            )

    def usage_signals(self, organization_id: UUID, asset_id: UUID) -> tuple[UsageSignal, ...]:
        self._assert_org(organization_id)
        rows = self.session.execute(
            text("""
                SELECT * FROM asset_intelligence_usage_signals
                WHERE organization_id=:organization_id AND asset_id=:asset_id
                ORDER BY occurred_at, id
            """),
            {"organization_id": organization_id, "asset_id": asset_id},
        ).mappings().all()
        return tuple(
            UsageSignal(
                id=row["id"],
                organization_id=row["organization_id"],
                asset_id=row["asset_id"],
                signal=row["signal"],
                occurred_at=row["occurred_at"],
                project_id=row["project_id"],
                actor_id=row["actor_id"],
                training_authorization_granted=bool(
                    row["training_authorization_granted"]
                ),
            )
            for row in rows
        )

    def mark_deleted(self, organization_id: UUID, asset_id: UUID, deleted_at: object) -> None:
        self._assert_org(organization_id)
        with self._transaction():
            self.session.execute(
                text("""
                    UPDATE asset_intelligence_analysis
                    SET state='DELETING', deleted_at=:deleted_at
                    WHERE organization_id=:organization_id AND asset_id=:asset_id
                """),
                {
                    "organization_id": organization_id,
                    "asset_id": asset_id,
                    "deleted_at": deleted_at,
                },
            )

    def reconcile_deleted(self, organization_id: UUID, asset_id: UUID) -> int:
        self._assert_org(organization_id)
        with self._transaction():
            count = self.session.execute(
                text("""
                    DELETE FROM asset_intelligence_analysis
                    WHERE organization_id=:organization_id AND asset_id=:asset_id
                    RETURNING id
                """),
                {"organization_id": organization_id, "asset_id": asset_id},
            ).all()
            self.session.execute(
                text("""
                    DELETE FROM asset_intelligence_usage_signals
                    WHERE organization_id=:organization_id AND asset_id=:asset_id
                """),
                {"organization_id": organization_id, "asset_id": asset_id},
            )
            return len(count)
