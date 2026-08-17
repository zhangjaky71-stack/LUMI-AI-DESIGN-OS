from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .contracts import (
    AssetRightsSnapshot,
    BrandGuideProposal,
    BrandRuleSet,
    ProposalStatus,
    RuleSetStatus,
    RuleSource,
)
from .ports import AssetRightsReader, BrandRuleRepository


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PostgresBrandRuleRepository(BrandRuleRepository):
    """Tenant-scoped persistence for immutable NODE-43 brand snapshots."""

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
            raise ValueError("cross-tenant brand repository access denied")



    def next_version(self, organization_id: UUID, brand_id: UUID) -> int:
        self._assert_org(organization_id)
        with self._transaction():
            row = self.session.execute(
                text(
                    """
                    INSERT INTO brand_rule_version_counters (
                        organization_id, brand_id, next_version
                    )
                    VALUES (:organization_id, :brand_id, 1)
                    ON CONFLICT (brand_id) DO UPDATE
                    SET next_version = brand_rule_version_counters.next_version + 1
                    WHERE brand_rule_version_counters.organization_id = EXCLUDED.organization_id
                    RETURNING next_version
                    """
                ),
                {"organization_id": organization_id, "brand_id": brand_id},
            ).mappings().one_or_none()
            if row is None:
                raise ValueError("brand version counter tenant mismatch")
            return int(row["next_version"])

    def save_rule_set(self, value: BrandRuleSet) -> None:
        self._assert_org(value.organization_id)
        with self._transaction():
            current = self.session.execute(
                text(
                    """
                    SELECT snapshot_hash, status
                    FROM brand_rule_set_versions
                    WHERE id=:id AND organization_id=:organization_id
                    FOR UPDATE
                    """
                ),
                {"id": value.id, "organization_id": value.organization_id},
            ).mappings().one_or_none()
            if current is None:
                self.session.execute(
                    text(
                        """
                        INSERT INTO brand_rule_set_versions (
                            id, organization_id, brand_id, version_number, status,
                            source, snapshot_hash, token_set_json, asset_set_json,
                            rules_json, voice_json, visual_style_json,
                            source_proposal_id, created_by, created_at, published_at, published_by
                        ) VALUES (
                            :id, :organization_id, :brand_id, :version_number, :status,
                            :source, :snapshot_hash, CAST(:token_set_json AS jsonb),
                            CAST(:asset_set_json AS jsonb), CAST(:rules_json AS jsonb),
                            CAST(:voice_json AS jsonb), CAST(:visual_style_json AS jsonb),
                            :source_proposal_id, :created_by, :created_at,
                            :published_at, :published_by
                        )
                        """
                    ),
                    self._rule_set_params(value),
                )
            else:
                if current["snapshot_hash"] != value.snapshot_hash:
                    raise ValueError("brand rule set snapshot content is immutable")
                if current["status"] in {"published", "retired"}:
                    if current["status"] != value.status.value.lower():
                        raise ValueError("published/retired brand rule set is immutable")
                    return
                self.session.execute(
                    text(
                        """
                        UPDATE brand_rule_set_versions
                        SET status=:status, published_at=:published_at, published_by=:published_by
                        WHERE id=:id AND organization_id=:organization_id
                        """
                    ),
                    {
                        "id": value.id,
                        "organization_id": value.organization_id,
                        "status": value.status.value.lower(),
                        "published_at": value.published_at,
                        "published_by": value.published_by,
                    },
                )

    def get_rule_set(
        self, organization_id: UUID, rule_set_id: UUID
    ) -> BrandRuleSet | None:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(
                """
                SELECT *
                FROM brand_rule_set_versions
                WHERE id=:id AND organization_id=:organization_id
                """
            ),
            {"id": rule_set_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        return None if row is None else self._rule_set(row)

    def get_active_rule_set(
        self, organization_id: UUID, brand_id: UUID
    ) -> BrandRuleSet | None:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(
                """
                SELECT r.*
                FROM brands b
                JOIN brand_rule_set_versions r ON r.id=b.active_rule_set_version_id
                WHERE b.id=:brand_id
                  AND b.organization_id=:organization_id
                  AND r.organization_id=:organization_id
                  AND b.deleted_at IS NULL
                """
            ),
            {"brand_id": brand_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        return None if row is None else self._rule_set(row)

    def set_active_rule_set(
        self, organization_id: UUID, brand_id: UUID, rule_set_id: UUID
    ) -> None:
        self._assert_org(organization_id)
        with self._transaction():
            result = self.session.execute(
                text(
                    """
                    UPDATE brands b
                    SET active_rule_set_version_id=:rule_set_id,
                        updated_at=now(),
                        version=version+1
                    WHERE b.id=:brand_id
                      AND b.organization_id=:organization_id
                      AND b.deleted_at IS NULL
                      AND EXISTS (
                        SELECT 1 FROM brand_rule_set_versions r
                        WHERE r.id=:rule_set_id
                          AND r.brand_id=b.id
                          AND r.organization_id=b.organization_id
                          AND r.status='published'
                      )
                    """
                ),
                {
                    "rule_set_id": rule_set_id,
                    "brand_id": brand_id,
                    "organization_id": organization_id,
                },
            )
            if result.rowcount != 1:
                raise ValueError("published rule set does not belong to brand")

    def save_proposal(self, value: BrandGuideProposal) -> None:
        self._assert_org(value.organization_id)
        with self._transaction():
            current = self.session.execute(
                text(
                    """
                    SELECT id FROM brand_guide_proposals
                    WHERE id=:id AND organization_id=:organization_id
                    FOR UPDATE
                    """
                ),
                {"id": value.id, "organization_id": value.organization_id},
            ).one_or_none()
            params = {
                "id": value.id,
                "organization_id": value.organization_id,
                "brand_id": value.brand_id,
                "source_asset_id": value.source_asset_id,
                "status": value.status.value.lower(),
                "rules_json": _json(value.rules),
                "citations_json": _json(value.citations),
                "created_at": value.created_at,
                "reviewed_by": value.reviewed_by,
                "reviewed_at": value.reviewed_at,
            }
            if current is None:
                self.session.execute(
                    text(
                        """
                        INSERT INTO brand_guide_proposals (
                            id, organization_id, brand_id, source_asset_id, status,
                            rules_json, citations_json, created_at, reviewed_by, reviewed_at
                        ) VALUES (
                            :id, :organization_id, :brand_id, :source_asset_id, :status,
                            CAST(:rules_json AS jsonb), CAST(:citations_json AS jsonb),
                            :created_at, :reviewed_by, :reviewed_at
                        )
                        """
                    ),
                    params,
                )
            else:
                self.session.execute(
                    text(
                        """
                        UPDATE brand_guide_proposals
                        SET status=:status, reviewed_by=:reviewed_by,
                            reviewed_at=:reviewed_at
                        WHERE id=:id AND organization_id=:organization_id
                        """
                    ),
                    params,
                )

    def get_proposal(
        self, organization_id: UUID, proposal_id: UUID
    ) -> BrandGuideProposal | None:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(
                """
                SELECT *
                FROM brand_guide_proposals
                WHERE id=:id AND organization_id=:organization_id
                """
            ),
            {"id": proposal_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        return BrandGuideProposal(
            id=row["id"],
            organization_id=row["organization_id"],
            brand_id=row["brand_id"],
            source_asset_id=row["source_asset_id"],
            status=ProposalStatus(str(row["status"]).upper()),
            rules=tuple(row["rules_json"]),
            citations=tuple(row["citations_json"]),
            created_at=row["created_at"],
            reviewed_by=row["reviewed_by"],
            reviewed_at=row["reviewed_at"],
        )

    @staticmethod
    def _rule_set_params(value: BrandRuleSet) -> dict[str, Any]:
        return {
            "id": value.id,
            "organization_id": value.organization_id,
            "brand_id": value.brand_id,
            "version_number": value.version,
            "status": value.status.value.lower(),
            "source": value.source.value,
            "snapshot_hash": value.snapshot_hash,
            "token_set_json": _json(value.token_set),
            "asset_set_json": _json(value.asset_set),
            "rules_json": _json(value.rules),
            "voice_json": _json(value.voice),
            "visual_style_json": _json(value.visual_style),
            "source_proposal_id": value.source_proposal_id,
            "created_by": value.created_by,
            "created_at": value.created_at,
            "published_at": value.published_at,
            "published_by": value.published_by,
        }

    @staticmethod
    def _rule_set(row: Mapping[str, Any]) -> BrandRuleSet:
        return BrandRuleSet(
            id=row["id"],
            organization_id=row["organization_id"],
            brand_id=row["brand_id"],
            version=row["version_number"],
            status=RuleSetStatus(str(row["status"]).upper()),
            source=RuleSource(row["source"]),
            token_set=row["token_set_json"],
            asset_set=row["asset_set_json"],
            rules=tuple(row["rules_json"]),
            voice=row["voice_json"],
            visual_style=row["visual_style_json"],
            source_proposal_id=row["source_proposal_id"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            published_at=row["published_at"],
            published_by=row["published_by"],
            snapshot_hash=row["snapshot_hash"],
        )



class PostgresAssetRightsReader(AssetRightsReader):
    """Read NODE-18 asset readiness and rights without trusting client metadata."""

    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    def read(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetRightsSnapshot:
        if organization_id != self.organization_id:
            return AssetRightsSnapshot(asset_id=asset_id, exists=False, ready=False)
        row = self.session.execute(
            text(
                """
                SELECT a.id, a.status, a.media_kind,
                       r.rights_level, r.commercial_use
                FROM assets a
                LEFT JOIN asset_rights r
                  ON r.asset_id=a.id
                 AND r.organization_id=a.organization_id
                WHERE a.id=:asset_id
                  AND a.organization_id=:organization_id
                  AND a.deleted_at IS NULL
                """
            ),
            {
                "asset_id": asset_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            return AssetRightsSnapshot(asset_id=asset_id, exists=False, ready=False)
        return AssetRightsSnapshot(
            asset_id=row["id"],
            exists=True,
            ready=str(row["status"]) == "ready",
            media_kind=row["media_kind"],
            rights_level=row["rights_level"],
            commercial_use=row["commercial_use"],
        )
