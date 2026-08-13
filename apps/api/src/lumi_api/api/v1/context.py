from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import Header, Query, Request
from lumi_domain import ProjectStatus
from lumi_project_core import ProjectListFilter

from .errors import ApiProblem

_ETAG_VERSION = re.compile(r'^(?:W/)?"?(?P<version>[1-9][0-9]*)"?$')


@dataclass(frozen=True, slots=True)
class RequestContext:
    organization_id: UUID
    request_id: str
    actor_id: UUID | None = None
    actor_type: str = "contract_only"
    permissions: frozenset[str] = field(default_factory=frozenset)
    trace_id: str | None = None
    api_token_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PageRequest:
    cursor: str | None
    limit: int


def get_request_context(
    request: Request,
    organization_id: Annotated[
        UUID,
        Header(
            alias="X-Lumi-Organization-Id",
            description=(
                "Tenant selector. This header is never authorization by itself; NODE-16 "
                "must validate the authenticated actor has membership in this organization."
            ),
        ),
    ],
) -> RequestContext:
    request_id = str(getattr(request.state, "request_id", "missing-request-id"))
    return RequestContext(organization_id=organization_id, request_id=request_id)


def get_page_request(
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PageRequest:
    return PageRequest(cursor=cursor, limit=limit)


def get_project_list_filter(
    status: Annotated[ProjectStatus | None, Query()] = None,
    workspace_id: Annotated[UUID | None, Query()] = None,
    created_by: Annotated[UUID | None, Query()] = None,
    updated_after: Annotated[datetime | None, Query()] = None,
    updated_before: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> ProjectListFilter:
    return ProjectListFilter(
        status=cast(object, status.value.upper()) if status is not None else None,  # type: ignore[arg-type]
        workspace_id=str(workspace_id) if workspace_id else None,
        created_by=str(created_by) if created_by else None,
        updated_after=updated_after,
        updated_before=updated_before,
        name_query=q,
    )


def require_idempotency_key(
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=512,
            description="Stable client-generated key for retry-safe side effects.",
        ),
    ] = None,
) -> str:
    if idempotency_key is None:
        raise ApiProblem(
            status=428,
            code="IDEMPOTENCY_KEY_REQUIRED",
            title="Idempotency-Key required",
            detail="This operation can create a durable side effect and requires Idempotency-Key.",
        )
    return idempotency_key


def require_if_match_version(
    if_match: Annotated[
        str | None,
        Header(
            alias="If-Match",
            description='Expected optimistic-lock version, e.g. `"3"` or `W/"3"`.',
        ),
    ] = None,
) -> int:
    if if_match is None:
        raise ApiProblem(
            status=428,
            code="IF_MATCH_REQUIRED",
            title="If-Match required",
            detail="Mutable resource updates require an expected version.",
        )
    match = _ETAG_VERSION.fullmatch(if_match.strip())
    if match is None:
        raise ApiProblem(
            status=400,
            code="INVALID_IF_MATCH",
            title="Invalid If-Match",
            detail='Use a positive integer entity version such as `"3"`.',
        )
    return int(match.group("version"))


def version_etag(version: int) -> str:
    if version < 1:
        raise ValueError("entity version must be >= 1")
    return f'W/"{version}"'
