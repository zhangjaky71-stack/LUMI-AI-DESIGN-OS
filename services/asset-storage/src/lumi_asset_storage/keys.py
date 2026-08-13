from __future__ import annotations

import re
from pathlib import PurePath

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._() -]+")


def asset_object_key(
    *,
    organization_id: str,
    project_id: str | None,
    asset_id: str,
    variant: str,
    file_id: str,
) -> str:
    for label, value in (
        ("organization_id", organization_id),
        ("asset_id", asset_id),
        ("variant", variant),
        ("file_id", file_id),
    ):
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"invalid {label}")
    project_segment = project_id or "unscoped"
    if "/" in project_segment or "\\" in project_segment or project_segment in {".", ".."}:
        raise ValueError("invalid project_id")
    return (
        f"org/{organization_id}/project/{project_segment}/asset/{asset_id}/"
        f"{variant}/{file_id}"
    )


def sanitize_download_filename(value: str | None, *, fallback: str = "download") -> str:
    if not value:
        return fallback
    basename = PurePath(value.replace("\\", "/")).name.strip().replace("\x00", "")
    cleaned = _SAFE_FILENAME.sub("_", basename).strip(" .")
    if not cleaned:
        return fallback
    return cleaned[:180]
