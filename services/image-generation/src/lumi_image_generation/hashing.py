from __future__ import annotations

from .model import ImageGenerationSpec, canonical_hash


def constraint_snapshot_hash(spec: ImageGenerationSpec) -> str:
    return canonical_hash(
        [
            {
                "constraint_id": item.constraint_id,
                "constraint_type": item.constraint_type,
                "severity": item.severity,
                "snapshot_hash": item.snapshot_hash,
                "parameters": dict(item.parameters),
            }
            for item in sorted(spec.constraints, key=lambda value: value.constraint_id)
        ]
    )
