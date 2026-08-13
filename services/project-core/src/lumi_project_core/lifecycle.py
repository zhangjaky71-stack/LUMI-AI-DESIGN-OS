from __future__ import annotations

from typing import Literal

ProjectStatus = Literal["draft", "active", "paused", "archived"]


def can_archive(status: ProjectStatus) -> bool:
    return status in {"draft", "active", "paused"}


def archive(status: ProjectStatus) -> ProjectStatus:
    if not can_archive(status):
        raise ValueError("PROJECT_ALREADY_ARCHIVED")
    return "archived"


def restore(status: ProjectStatus) -> ProjectStatus:
    """Restore is an explicit administrative command, not an ordinary state transition.

    Restored projects return paused so recovery never silently re-enables paid generation.
    The user must explicitly activate the project afterwards.
    """
    if status != "archived":
        raise ValueError("PROJECT_NOT_ARCHIVED")
    return "paused"


def can_modify(status: ProjectStatus, *, deleted: bool) -> bool:
    return not deleted and status != "archived"


def can_start_paid_command(status: ProjectStatus, *, deleted: bool) -> bool:
    return not deleted and status == "active"


def require_mutable(status: ProjectStatus, *, deleted: bool) -> None:
    if deleted:
        raise ValueError("PROJECT_DELETED")
    if status == "archived":
        raise ValueError("PROJECT_ARCHIVED")


def require_paid_command_allowed(status: ProjectStatus, *, deleted: bool) -> None:
    if deleted:
        raise ValueError("PROJECT_DELETED")
    if status != "active":
        raise ValueError("PROJECT_NOT_ACTIVE")
