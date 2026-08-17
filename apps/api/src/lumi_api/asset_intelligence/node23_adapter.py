from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_asset_intelligence import EmbeddingCapability


class Node23CapabilityRegistryAdapter:
    """Resolve one version-pinned multimodal embedding candidate from NODE-23 tables."""

    capability_key = "embedding.multimodal"

    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_multimodal_embedding(self, organization_id: UUID) -> EmbeddingCapability:
        del organization_id  # registry is global; tenant policy is applied by the caller/router.
        row: Mapping[str, Any] | None = self.session.execute(
            text("""
                SELECT d.model_key, r.revision_key, r.registry_version_id,
                       c.capability_key, c.support, c.confidence, c.limits,
                       c.source_ref
                FROM model_capability_claims c
                JOIN model_revisions r ON r.id = c.model_revision_id
                JOIN model_definitions d ON d.id = r.model_definition_id
                JOIN model_registry_versions v ON v.id = r.registry_version_id
                WHERE c.capability_key = :capability_key
                  AND c.support IN ('full','partial')
                  AND r.route_eligible = true
                  AND v.status = 'published'
                ORDER BY
                  CASE c.support WHEN 'full' THEN 0 ELSE 1 END,
                  c.observed_at DESC,
                  r.revision_key ASC
                LIMIT 1
            """),
            {"capability_key": self.capability_key},
        ).mappings().one_or_none()
        if row is None:
            raise LookupError("MULTIMODAL_EMBEDDING_CAPABILITY_NOT_FOUND")
        limits = row["limits"] or {}
        dimensions = int(limits.get("dimensions", 0))
        embedding_version = str(limits.get("embedding_version", ""))
        if dimensions <= 0 or not embedding_version:
            raise ValueError("MULTIMODAL_EMBEDDING_CLAIM_INCOMPLETE")
        return EmbeddingCapability(
            model_key=str(row["model_key"]),
            revision_key=str(row["revision_key"]),
            registry_version_id=row["registry_version_id"],
            capability_key=str(row["capability_key"]),
            support=str(row["support"]),
            confidence=str(row["confidence"]),
            embedding_version=embedding_version,
            dimensions=dimensions,
            source_ref=str(row["source_ref"]),
        )
