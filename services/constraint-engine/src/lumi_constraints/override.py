from __future__ import annotations

from datetime import UTC, datetime

from .model import Constraint, OverrideAudit


class OverrideDenied(PermissionError):
    pass


def create_override_audit(
    constraint: Constraint,
    *,
    override_id: str,
    actor_id: str,
    reason: str,
    authorized: bool,
    occurred_at: datetime | None = None,
) -> OverrideAudit:
    if not override_id or not actor_id or not reason.strip():
        raise OverrideDenied("override requires id, actor and non-empty reason")
    if not authorized:
        raise OverrideDenied("actor is not authorized to override this constraint")
    if constraint.source == "SAFETY_SYSTEM" or constraint.override_policy == "NEVER":
        raise OverrideDenied("constraint cannot be overridden")
    return OverrideAudit(
        override_id=override_id,
        constraint_id=constraint.id,
        actor_id=actor_id,
        reason=reason.strip(),
        occurred_at=occurred_at or datetime.now(UTC),
        authorized=True,
    )
