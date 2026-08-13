from __future__ import annotations

from .context import ApplicationContext
from .ports import AuthorizationPort


async def require_access(
    authorizer: AuthorizationPort,
    context: ApplicationContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
) -> None:
    if context.actor_id is None:
        raise PermissionError("authenticated actor is required for this use case")
    await authorizer.require(
        context,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
