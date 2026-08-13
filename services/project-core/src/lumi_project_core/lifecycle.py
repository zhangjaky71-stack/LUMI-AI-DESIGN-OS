from __future__ import annotations

from typing import Literal, cast

ProjectStatus = Literal["draft", "active", "paused", "archived"]
_ALLOWED = frozenset({"draft", "active", "paused", "archived"})


def normalize_status(status: str) -> ProjectStatus:
    normalized = status.strip().lower()
    if normalized not in _ALLOWED:
        raise ValueError("PROJECT_STATUS_INVALID")
    return cast(ProjectStatus, normalized)


def can_archive(status: str) -> bool:
    return normalize_status(status) in {"draft", "active", "paused"}


def archive(status: str) -> ProjectStatus:
    if not can_archive(status):
        raise ValueError("PROJECT_ALREADY_ARCHIVED")
    return "archived"


def restore(status: str) -> ProjectStatus:
    """Restore is an explicit administrative command, not an ordinary state transition.

    Restored projects return paused so recovery never silently re-enables paid generation.
    The user must explicitly activate the project afterwards.
    """
    if normalize_status(status) != "archived":
        raise ValueError("PROJECT_NOT_ARCHIVED")
    return "paused"


def can_modify(status: str, *, deleted: bool) -> bool:
    return not deleted and normalize_status(status) != "archived"


def can_start_paid_command(status: str, *, deleted: bool) -> bool:
    return not deleted and normalize_status(status) == "active"


def require_mutable(status: str, *, deleted: bool) -> None:
    if deleted:
        raise ValueError("PROJECT_DELETED")
    if normalize_status(status) == "archived":
        raise ValueError("PROJECT_ARCHIVED")


def require_paid_command_allowed(status: str, *, deleted: bool) -> None:
    if deleted:
        raise ValueError("PROJECT_DELETED")
    if normalize_status(status) != "active":
        raise ValueError("PROJECT_NOT_ACTIVE")
