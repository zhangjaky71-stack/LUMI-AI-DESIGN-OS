from __future__ import annotations

import hashlib
import json

from .model import EditValidationReport, ImageEditSpec


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constraint_snapshot_hash(spec: ImageEditSpec) -> str:
    return canonical_hash(tuple(sorted(spec.constraints, key=lambda item: item.constraint_id)))


def protected_region_hash(spec: ImageEditSpec) -> str:
    return canonical_hash(tuple(sorted(spec.protected_regions, key=lambda item: item.region_id)))


def validation_report_hash(report: EditValidationReport) -> str:
    return canonical_hash(report)
