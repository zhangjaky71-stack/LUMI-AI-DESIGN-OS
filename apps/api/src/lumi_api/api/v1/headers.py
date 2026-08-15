from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header

OrganizationId = Annotated[
    UUID,
    Header(
        alias="X-Organization-ID",
        description="Tenant organization selected for this request.",
    ),
]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=255,
        description="Tenant-scoped key for retry-safe side effects.",
    ),
]
IfMatch = Annotated[
    str,
    Header(
        alias="If-Match",
        description='Optimistic concurrency ETag, for example W/"7".',
    ),
]
