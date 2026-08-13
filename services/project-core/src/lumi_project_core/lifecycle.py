from __future__ import annotations

from typing import Literal

ProjectStatus = Literal["DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"]


def can_archive(status: ProjectStatus) -> bool:
    return status in {"DRAFT", "ACTIVE", "PAUSED"}


def archive(status: ProjectStatus) -> ProjectStatus:
    if not can_archive(status):
        raise ValueError("PROJECT_ALREADY_ARCHIVED")
    return "ARCHIVED"


def can_modify(status: ProjectStatus, *, deleted: bool) -> bool:
    return not deleted and status != "ARCHIVED"


def require_mutable(status: ProjectStatus, *, deleted: bool) -> None:
    if deleted:
        raise ValueError("PROJECT_DELETED")
    if status == "ARCHIVED":
        raise ValueError("PROJECT_ARCHIVED")
