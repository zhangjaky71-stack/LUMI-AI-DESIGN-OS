from __future__ import annotations

from collections.abc import Iterable

from .model import Constraint, ConstraintScope


SUPPORTED_PROTECTIONS = frozenset({"position", "size", "rotation", "transform", "content", "text", "asset", "identity", "style", "brand", "scannability"})

PROTECTION_TYPES = {
    "position": "LOCK_POSITION",
    "size": "LOCK_SIZE",
    "rotation": "LOCK_ROTATION",
    "transform": "LOCK_TRANSFORM",
    "content": "LOCK_CONTENT",
    "text": "LOCK_TEXT",
    "asset": "LOCK_ASSET",
    "identity": "LOCK_IDENTITY",
    "style": "LOCK_STYLE",
    "brand": "LOCK_BRAND",
    "scannability": "REQUIRE_SCANNABILITY",
}


def compile_user_explicit_protections(
    *,
    target_id: str,
    protections: Iterable[str],
    id_prefix: str,
    priority: int = 1000,
) -> tuple[Constraint, ...]:
    """Convert a structured intent-parser result into enforceable USER_EXPLICIT constraints.

    Natural-language parsing is intentionally outside this function. The server-side boundary accepts only
    structured protections, so prompt interpretation is never the enforcement mechanism.
    """
    normalized = tuple(dict.fromkeys(protections))
    unknown = sorted(set(normalized) - SUPPORTED_PROTECTIONS)
    if unknown:
        raise ValueError(f"unsupported explicit protection(s): {unknown}")
    return tuple(
        Constraint(
            id=f"{id_prefix}:{target_id}:{PROTECTION_TYPES[protection].lower()}",
            type=PROTECTION_TYPES[protection],
            scope=ConstraintScope(node_ids=(target_id,)),
            severity="HARD",
            source="USER_EXPLICIT",
            priority=priority,
            parameters={},
            active=True,
            override_policy="AUTHORIZED",
        )
        for protection in normalized
    )
