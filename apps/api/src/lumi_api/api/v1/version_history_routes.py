from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Request, status

from lumi_api.artifact_engine import ProvenanceEnvelope
from lumi_api.artifacts.models import ArtifactBranch, CreatedByType, ProvenanceRecord

from .artifact_engine_dependencies import ArtifactEngineServiceDependency
from .artifact_engine_routes import _invoke, _scope
from .artifact_engine_schemas import (
    ArtifactVersionHistoryItem,
    ArtifactVersionHistoryResponse,
    SafeSkillVersion,
    SafeVersionProvenanceResponse,
    UserForkVersionRequest,
    UserRestoreVersionRequest,
    VersionPreviewSummary,
)
from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _actor_id(request: Request) -> str:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Version fork and restore require an authenticated actor.",
        )
    return str(actor_id)


def _preview(version) -> VersionPreviewSummary:
    primary = None
    if version.primary_file_id is not None:
        primary = next(
            (item for item in version.files if item.id == version.primary_file_id),
            None,
        )
    if primary is None:
        primary = next(
            (item for item in version.files if item.role.value == "preview"),
            None,
        )
    if primary is None:
        return VersionPreviewSummary()
    return VersionPreviewSummary(
        mime_type=primary.mime_type,
        width=primary.width,
        height=primary.height,
        duration_ms=primary.duration_ms,
    )


def _history_item(version) -> ArtifactVersionHistoryItem:
    return ArtifactVersionHistoryItem(
        id=version.id,
        artifact_id=version.artifact_id,
        branch_id=version.branch_id,
        parent_version_id=version.parent_version_id,
        version_number=version.version_number,
        status=version.status,
        content_hash=version.content_hash,
        design_document_version_id=version.design_document_version_id,
        quality_score=version.quality_score,
        constraint_snapshot_hash=version.constraint_snapshot_hash,
        created_by_type=version.created_by_type,
        created_by_id=version.created_by_id,
        created_at=version.created_at,
        preview=_preview(version),
    )


@router.get(
    "/artifacts/{artifact_id}/version-history",
    response_model=ArtifactVersionHistoryResponse,
    responses=_ERROR_RESPONSES,
    tags=["version-history"],
)
def get_artifact_version_history(
    artifact_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersionHistoryResponse:
    artifact = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_artifact(artifact_id)),
    )
    branches = tuple(
        _scope(organization_id, item)
        for item in _invoke(lambda: service.repository.list_branches(artifact.id))
    )
    versions = tuple(
        _scope(organization_id, item)
        for item in _invoke(lambda: service.repository.list_versions(artifact.id))
    )
    return ArtifactVersionHistoryResponse(
        artifact=artifact,
        branches=branches,
        versions=tuple(_history_item(item) for item in versions),
    )


@router.get(
    "/artifacts/{artifact_id}/branches",
    response_model=list[ArtifactBranch],
    responses=_ERROR_RESPONSES,
    tags=["version-history"],
)
def list_artifact_branches(
    artifact_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> list[ArtifactBranch]:
    artifact = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_artifact(artifact_id)),
    )
    return [
        _scope(organization_id, item)
        for item in _invoke(lambda: service.repository.list_branches(artifact.id))
    ]


@router.get(
    "/artifact-versions/{version_id}/provenance-safe",
    response_model=SafeVersionProvenanceResponse,
    responses=_ERROR_RESPONSES,
    tags=["version-history"],
)
def get_safe_version_provenance(
    version_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> SafeVersionProvenanceResponse:
    version = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    envelope = _invoke(lambda: service.repository.get_provenance_envelope(version.id))
    completeness = _invoke(
        lambda: service.repository.get_provenance_completeness(version.id)
    )
    record = envelope.record
    return SafeVersionProvenanceResponse(
        artifact_version_id=version.id,
        traceability_score=float(completeness.score),
        traceability_status=completeness.status.value,
        missing_fields=completeness.missing_fields,
        agent_run_id=record.agent_run_id,
        task_id=record.task_id,
        generation_id=record.generation_id,
        provider=record.provider,
        model=record.model,
        prompt_hash=record.prompt_hash,
        prompt_template_version=record.prompt_template_version,
        input_asset_ids=record.input_asset_ids,
        input_artifact_version_ids=record.input_artifact_version_ids,
        design_ir_schema_version=record.design_ir_schema_version,
        constraint_snapshot_hash=record.constraint_snapshot_hash,
        recipe_version=record.recipe_version,
        skill_versions=tuple(
            SafeSkillVersion(skill_id=item.skill_id, version=item.version)
            for item in record.skill_versions
        ),
        code_git_sha=record.code_git_sha,
        compiler_version=envelope.compiler_version,
        agent_version=envelope.agent_version,
    )


@router.post(
    "/artifact-versions/{version_id}/fork-user",
    response_model=ArtifactBranch,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["version-history"],
)
def fork_artifact_version_for_user(
    version_id: UUID,
    body: UserForkVersionRequest,
    request: Request,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactBranch:
    source = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    return _scope(
        organization_id,
        _invoke(
            lambda: service.fork_version(
                source.id,
                name=body.name.strip(),
                created_by_type=CreatedByType.USER,
                created_by_id=_actor_id(request),
                created_at=datetime.now(timezone.utc),
            )
        ),
    )


@router.post(
    "/artifact-versions/{version_id}/restore-user",
    response_model=ArtifactVersionHistoryItem,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["version-history"],
)
def restore_artifact_version_for_user(
    version_id: UUID,
    body: UserRestoreVersionRequest,
    request: Request,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersionHistoryItem:
    source = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    target = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_branch(body.target_branch_id)),
    )
    source_envelope = _invoke(
        lambda: service.repository.get_provenance_envelope(source.id)
    )
    provenance = ProvenanceEnvelope(
        record=ProvenanceRecord(
            input_artifact_version_ids=(source.id,),
            design_ir_schema_version=source.provenance.design_ir_schema_version,
            constraint_snapshot_hash=source.constraint_snapshot_hash,
            code_git_sha=source.provenance.code_git_sha,
        ),
        compiler_version=source_envelope.compiler_version,
    )
    restored, _ = _invoke(
        lambda: service.restore_version(
            source.id,
            target_branch_id=target.id,
            expected_head_version_id=body.expected_head_version_id,
            provenance=provenance,
            created_by_type=CreatedByType.USER,
            created_by_id=_actor_id(request),
            created_at=datetime.now(timezone.utc),
        )
    )
    return _history_item(_scope(organization_id, restored))
