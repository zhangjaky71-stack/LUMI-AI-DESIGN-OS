from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .models import Principal, RequestContext


class TenantOwned(Protocol):
    organization_id: UUID


class TenantAccessDenied(LookupError):
    pass


def require_tenant_resource(
    organization_id: UUID,
    resource: TenantOwned | None,
) -> TenantOwned:
    if resource is None or resource.organization_id != organization_id:
        # Deliberately one outward category for absent and cross-tenant IDs.
        raise TenantAccessDenied("TENANT_RESOURCE_NOT_FOUND")
    return resource


def require_principal_tenant(
    principal: Principal,
    organization_id: UUID,
) -> None:
    if principal.organization_id != organization_id:
        raise TenantAccessDenied("TENANT_RESOURCE_NOT_FOUND")


def build_request_context(
    *,
    principal: Principal,
    request_id: str,
    trace_id: str,
    organization_id: UUID,
    workspace_id: UUID | None = None,
) -> RequestContext:
    require_principal_tenant(principal, organization_id)
    return RequestContext(
        request_id=request_id,
        trace_id=trace_id,
        actor_id=principal.actor_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        roles=principal.roles,
        permissions=principal.permissions,
    )
