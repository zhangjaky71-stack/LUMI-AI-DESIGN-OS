from __future__ import annotations

from dataclasses import replace

from .model import EditJob
from .pipeline_support import ImageEditPipelineError


async def approve_mask(
    pipeline,
    *,
    organization_id: str,
    edit_id_value: str,
    approved_by: str,
) -> EditJob:
    job = pipeline.repository.get(organization_id, edit_id_value)
    if not job or job.status != "AWAITING_MASK_APPROVAL":
        raise ValueError("IMAGE_EDIT_MASK_APPROVAL_STATE_INVALID")
    spec = pipeline.repository.get_spec(organization_id, edit_id_value)
    if not spec.mask or not spec.mask.preview_required:
        raise ValueError("IMAGE_EDIT_MASK_APPROVAL_NOT_REQUIRED")
    updated = replace(
        spec,
        mask=replace(spec.mask, preview_approved_by=approved_by),
    )
    if updated.semantic_hash != job.semantic_hash:
        raise ImageEditPipelineError(
            "IMAGE_EDIT_APPROVAL_CHANGED_SEMANTICS"
        )
    bind = getattr(pipeline.repository, "bind_spec", None)
    if not bind:
        raise RuntimeError("IMAGE_EDIT_REPOSITORY_SPEC_UPDATE_REQUIRED")
    bind(edit_id_value, updated)
    ready = replace(job, status="QUEUED", error_code=None)
    pipeline.repository.save(ready)
    await pipeline.events.emit(
        "image_edit.mask_approved",
        organization_id=organization_id,
        edit_id=edit_id_value,
        payload={"approved_by": approved_by},
    )
    return ready


async def confirm_broad_change(
    pipeline,
    *,
    organization_id: str,
    edit_id_value: str,
    confirmed_by: str,
) -> EditJob:
    job = pipeline.repository.get(organization_id, edit_id_value)
    if not job or job.status != "AWAITING_CONFIRMATION":
        raise ValueError("IMAGE_EDIT_CONFIRMATION_STATE_INVALID")
    spec = pipeline.repository.get_spec(organization_id, edit_id_value)
    updated = replace(
        spec,
        intent=replace(
            spec.intent,
            broad_change_confirmed=True,
            broad_change_confirmed_by=confirmed_by,
        ),
    )
    if updated.semantic_hash != job.semantic_hash:
        raise ImageEditPipelineError(
            "IMAGE_EDIT_CONFIRMATION_CHANGED_SEMANTICS"
        )
    bind = getattr(pipeline.repository, "bind_spec", None)
    if not bind:
        raise RuntimeError("IMAGE_EDIT_REPOSITORY_SPEC_UPDATE_REQUIRED")
    bind(edit_id_value, updated)
    ready = replace(job, status="QUEUED", error_code=None)
    pipeline.repository.save(ready)
    await pipeline.events.emit(
        "image_edit.broad_change_confirmed",
        organization_id=organization_id,
        edit_id=edit_id_value,
        payload={"confirmed_by": confirmed_by},
    )
    return ready


async def cancel(
    pipeline,
    *,
    organization_id: str,
    edit_id_value: str,
) -> EditJob:
    job = pipeline.repository.get(organization_id, edit_id_value)
    if not job:
        raise LookupError("IMAGE_EDIT_NOT_FOUND")
    pending = pipeline.repository.get_pending(edit_id_value)
    if pending:
        await pipeline.gateway.cancel(pending[1])
        pipeline.repository.delete_pending(edit_id_value)
    if job.status in {"COMPLETED", "REJECTED", "FAILED", "CANCELLED"}:
        return job
    cancelled = replace(job, status="CANCELLED")
    pipeline.repository.save(cancelled)
    return cancelled
