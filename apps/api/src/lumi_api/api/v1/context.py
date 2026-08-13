from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Header, Query, Request

from .errors import ApiProblem

_ETAG_VERSION = re.compile(r'^(?:W/)?"?(?P<version>[1-9][0-9]*)"?$')


@dataclass(frozen=True, slots=True)
class RequestContext:
    organization_id: UUID
    request_id: str


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
