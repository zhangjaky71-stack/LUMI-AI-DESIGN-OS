from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime


class CursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectCursor:
    created_at: datetime
    project_id: str


def encode_cursor(cursor: ProjectCursor) -> str:
    payload = {
        "v": 1,
        "created_at": cursor.created_at.isoformat(),
        "project_id": cursor.project_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> ProjectCursor:
    if not value or len(value) > 2048:
        raise CursorError("invalid cursor")
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise CursorError("unsupported cursor version")
        project_id = payload.get("project_id")
        created_at = payload.get("created_at")
        if not isinstance(project_id, str) or not project_id or not isinstance(created_at, str):
            raise CursorError("invalid cursor payload")
        return ProjectCursor(datetime.fromisoformat(created_at), project_id)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CursorError("invalid cursor") from exc
