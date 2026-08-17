from __future__ import annotations

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from .model import (
    EditFinding,
    GatewayEditResult,
    ImageEditSpec,
    SourceImageRef,
    canonical_hash,
)


def _with_provider_safety(
    report,
    result: GatewayEditResult,
):
    blocked = result.safety_metadata.get("blocked") is True or result.finish_reason in {
        "content_filter",
        "safety_block",
    }
    if not blocked:
        return report
    finding = EditFinding(
        "model-gateway-safety",
        "FAIL",
        "HARD",
        "IMAGE_EDIT_PROVIDER_SAFETY_BLOCK",
        evidence_ref=(
            f"provider:{result.provider};"
            f"request:{result.provider_request_id or 'unknown'}"
        ),
    )
    return replace(report, findings=report.findings + (finding,))


class ImageEditPipelineError(RuntimeError):
    pass


def edit_id(spec: ImageEditSpec) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{spec.organization_id}:{spec.operation_id}:image-edit",
        )
    )


def constraint_hash(spec: ImageEditSpec) -> str:
    return canonical_hash(
        [
            (constraint.constraint_id, constraint.snapshot_hash, constraint.severity)
            for constraint in spec.constraints
        ]
    )


def protected_hash(spec: ImageEditSpec) -> str:
    return canonical_hash(spec.protected_regions)


def instruction_hash(spec: ImageEditSpec) -> str:
    return canonical_hash(spec.intent.instruction)


def assert_source_unchanged(
    spec: ImageEditSpec,
    source: SourceImageRef,
) -> None:
    if (
        source.asset_version != spec.source.asset_version
        or source.checksum_sha256 != spec.source.checksum_sha256
        or source.artifact_version_id != spec.source.artifact_version_id
        or source.width != spec.source.width
        or source.height != spec.source.height
    ):
        raise ImageEditPipelineError("IMAGE_EDIT_SOURCE_CHANGED")
