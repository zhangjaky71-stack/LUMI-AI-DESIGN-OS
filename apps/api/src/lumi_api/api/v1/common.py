from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_ETAG_RE = re.compile(r'^(?:W/)?"?([1-9][0-9]*)"?$')
T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProblemDetail(StrictModel):
    type: str = "about:blank"
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    code: str
    request_id: str
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


class PageMeta(StrictModel):
    next_cursor: str | None = None
    has_more: bool = False


class Page(StrictModel, Generic[T]):
    items: list[T]
    meta: PageMeta


class VersionedResource(StrictModel):
    id: UUID
    organization_id: UUID
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


def parse_if_match(value: str) -> int:
    match = _ETAG_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError('If-Match must contain a positive integer ETag such as W/"7"')
    return int(match.group(1))


def version_etag(version: int) -> str:
    if version < 1:
        raise ValueError("version must be >= 1")
    return f'W/"{version}"'
