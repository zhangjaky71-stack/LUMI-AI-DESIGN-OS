from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True, slots=True)
class StorageObjectState:
    storage_key: str
    retention_until: datetime | None = None
    legal_hold: bool = False
    marked_at: datetime | None = None


def mark_unreferenced(
    objects: Iterable[StorageObjectState],
    *,
    live_storage_keys: set[str],
    now: datetime,
) -> tuple[StorageObjectState, ...]:
    result: list[StorageObjectState] = []
    for obj in objects:
        if obj.storage_key in live_storage_keys or obj.legal_hold:
            result.append(replace(obj, marked_at=None))
            continue
        if obj.retention_until is not None and now < obj.retention_until:
            result.append(replace(obj, marked_at=None))
            continue
        result.append(obj if obj.marked_at is not None else replace(obj, marked_at=now))
    return tuple(result)


def sweep_candidates(
    objects: Iterable[StorageObjectState],
    *,
    live_storage_keys: set[str],
    now: datetime,
    minimum_mark_delay: timedelta,
) -> tuple[StorageObjectState, ...]:
    """Second-pass delete candidates. Callers must still re-check storage/DB refs before delete."""
    candidates: list[StorageObjectState] = []
    for obj in objects:
        if obj.storage_key in live_storage_keys or obj.legal_hold or obj.marked_at is None:
            continue
        if obj.retention_until is not None and now < obj.retention_until:
            continue
        if now - obj.marked_at < minimum_mark_delay:
            continue
        candidates.append(obj)
    return tuple(sorted(candidates, key=lambda item: item.storage_key))


def confirm_delete(
    candidate: StorageObjectState,
    *,
    current_live_storage_keys: set[str],
    now: datetime,
    minimum_mark_delay: timedelta,
) -> bool:
    """Final safety check immediately before physical object deletion."""
    return bool(
        candidate.storage_key not in current_live_storage_keys
        and not candidate.legal_hold
        and candidate.marked_at is not None
        and now - candidate.marked_at >= minimum_mark_delay
        and (candidate.retention_until is None or now >= candidate.retention_until)
    )
