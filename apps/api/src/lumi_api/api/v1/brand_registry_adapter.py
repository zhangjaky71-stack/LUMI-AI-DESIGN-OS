from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .brand_registry_schemas import BrandCreateRequest, BrandPage, BrandPatchRequest, BrandResponse
from .errors import ApiProblem


class PostgresBrandRegistryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_brands(
        self,
        *,
        organization_id: UUID,
        limit: int,
        query: str | None,
    ) -> BrandPage:
        params: dict[str, Any] = {"organization_id": organization_id, "limit": limit}
        where = "organization_id=:organization_id AND deleted_at IS NULL"
        if query:
            where += " AND name ILIKE :query"
            params["query"] = f"%{query.strip()}%"
        rows = self.session.execute(
            text(
                f"""
                SELECT id, organization_id, name, profile_json,
                       active_rule_set_version_id, version, created_at, updated_at
                FROM brands
                WHERE {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        total = self.session.execute(
            text(f"SELECT count(*) FROM brands WHERE {where}"),
            {key: value for key, value in params.items() if key != "limit"},
        ).scalar_one()
        return BrandPage(items=[self._response(row) for row in rows], total=int(total))

    def create_brand(
        self,
        *,
        organization_id: UUID,
        request: BrandCreateRequest,
    ) -> BrandResponse:
        brand_id = new_uuid7()
        with self.session.begin():
            row = self.session.execute(
                text(
                    """
                    INSERT INTO brands (
                        id, organization_id, name, profile_json, version
                    ) VALUES (
                        :id, :organization_id, :name, CAST(:profile AS jsonb), 1
                    )
                    RETURNING id, organization_id, name, profile_json,
                              active_rule_set_version_id, version, created_at, updated_at
                    """
                ),
                {
                    "id": brand_id,
                    "organization_id": organization_id,
                    "name": request.name.strip(),
                    "profile": json.dumps(request.profile, sort_keys=True, separators=(",", ":")),
                },
            ).mappings().one()
        return self._response(row)

    def get_brand(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
    ) -> BrandResponse:
        row = self.session.execute(
            text(
                """
                SELECT id, organization_id, name, profile_json,
                       active_rule_set_version_id, version, created_at, updated_at
                FROM brands
                WHERE id=:brand_id
                  AND organization_id=:organization_id
                  AND deleted_at IS NULL
                """
            ),
            {"brand_id": brand_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise self._not_found()
        return self._response(row)

    def patch_brand(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        request: BrandPatchRequest,
        expected_version: int,
    ) -> BrandResponse:
        with self.session.begin():
            current = self.session.execute(
                text(
                    """
                    SELECT id, organization_id, name, profile_json,
                           active_rule_set_version_id, version, created_at, updated_at
                    FROM brands
                    WHERE id=:brand_id
                      AND organization_id=:organization_id
                      AND deleted_at IS NULL
                    FOR UPDATE
                    """
                ),
                {"brand_id": brand_id, "organization_id": organization_id},
            ).mappings().one_or_none()
            if current is None:
                raise self._not_found()
            if int(current["version"]) != expected_version:
                raise ApiProblem(
                    status=409,
                    code="brand_version_conflict",
                    title="Brand changed",
                    detail=(
                        f"Expected brand version {expected_version}, "
                        f"current version is {int(current['version'])}."
                    ),
                )
            name = request.name.strip() if request.name is not None else str(current["name"])
            profile = request.profile if request.profile is not None else dict(current["profile_json"] or {})
            row = self.session.execute(
                text(
                    """
                    UPDATE brands
                    SET name=:name,
                        profile_json=CAST(:profile AS jsonb),
                        version=version+1,
                        updated_at=now()
                    WHERE id=:brand_id
                      AND organization_id=:organization_id
                      AND deleted_at IS NULL
                      AND version=:expected_version
                    RETURNING id, organization_id, name, profile_json,
                              active_rule_set_version_id, version, created_at, updated_at
                    """
                ),
                {
                    "name": name,
                    "profile": json.dumps(profile, sort_keys=True, separators=(",", ":")),
                    "brand_id": brand_id,
                    "organization_id": organization_id,
                    "expected_version": expected_version,
                },
            ).mappings().one_or_none()
            if row is None:
                raise ApiProblem(
                    status=409,
                    code="brand_version_conflict",
                    title="Brand changed",
                    detail="The brand changed while this update was being applied.",
                )
        return self._response(row)

    @staticmethod
    def _response(row: Any) -> BrandResponse:
        return BrandResponse(
            id=row["id"],
            organization_id=row["organization_id"],
            name=row["name"],
            profile=dict(row["profile_json"] or {}),
            active_rule_set_version_id=row["active_rule_set_version_id"],
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _not_found() -> ApiProblem:
        return ApiProblem(
            status=404,
            code="brand_not_found",
            title="Brand not found",
            detail="The requested brand is unavailable in this organization.",
        )
