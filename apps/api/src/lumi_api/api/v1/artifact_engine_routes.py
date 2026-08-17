from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, TypeVar
from uuid import UUID

from fastapi import APIRouter, status

from lumi_api.artifact_engine import (
    ArtifactCompareResult,
    ArtifactCreateCommand,
    ArtifactEngineService,
    ArtifactHeadConflict,
    InitialVersionCreateCommand,
    ArtifactNotFound,
    ArtifactStorageViolation,
    VersionCreateCommand,
)
from lumi_api.artifacts.engine import ArtifactContractError, ArtifactGraphViolation
from lumi_api.artifacts.models import Artifact, ArtifactBranch, ArtifactVersion, LineageEdge

from .artifact_engine_dependencies import ArtifactEngineServiceDependency
from .artifact_engine_schemas import (
    ApproveVersionRequest,
    ArtifactBundleResponse,
    CreateArtifactRequest,
    CreateVersionRequest,
    ForkVersionRequest,
    MarkReadyRequest,
    RestoreVersionRequest,
)
from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1")
T = TypeVar("T")

_ERROR_RESPONSES = {
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invoke(call: Callable[[], T]) -> T:
    try:
        return call()
    except ArtifactNotFound as exc:
        raise ApiProblem(
            status=404,
            code="artifact_not_found",
            title="Artifact resource not found",
            detail=str(exc),
        ) from exc
    except ArtifactHeadConflict as exc:
        raise ApiProblem(
            status=409,
            code="artifact_head_conflict",
            title="Artifact branch or status changed",
            detail=str(exc),
        ) from exc
    except ArtifactStorageViolation as exc:
        raise ApiProblem(
            status=409,
            code="artifact_storage_violation",
            title="Artifact file verification failed",
            detail=str(exc),
        ) from exc
    except (ArtifactContractError, ArtifactGraphViolation, ValueError) as exc:
        raise ApiProblem(
            status=422,
            code="artifact_contract_violation",
            title="Artifact request violates the runtime contract",
            detail=str(exc),
        ) from exc


def _scope(organization_id: UUID, value: T) -> T:
    owner = getattr(value, "organization_id", organization_id)
    if owner != organization_id:
        raise ApiProblem(
            status=404,
            code="artifact_not_found",
            title="Artifact resource not found",
            detail="The requested resource is not available in this organization.",
        )
    return value


@router.post(
    "/projects/{project_id}/artifacts",
    response_model=ArtifactBundleResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def create_artifact(
    project_id: UUID,
    request: CreateArtifactRequest,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactBundleResponse:
    artifact, branch = _invoke(
        lambda: service.create_artifact(
            ArtifactCreateCommand(
                organization_id=organization_id,
                project_id=project_id,
                artifact_type=request.artifact_type,
                name=request.name,
                rights=request.rights,
                design_document_id=request.design_document_id,
                created_by_type=request.created_by_type,
                created_by_id=request.created_by_id,
                created_at=_now(),
                initial_version=(
                    InitialVersionCreateCommand(
                        content_hash=request.initial_version.content_hash,
                        files=request.initial_version.files,
                        provenance=request.initial_version.provenance,
                        rights=request.initial_version.rights,
                        created_by_type=request.initial_version.created_by_type,
                        created_by_id=request.initial_version.created_by_id,
                        primary_file_id=request.initial_version.primary_file_id,
                        design_document_version_id=(
                            request.initial_version.design_document_version_id
                        ),
                        quality_score=request.initial_version.quality_score,
                        constraint_snapshot_hash=request.initial_version.constraint_snapshot_hash,
                        lineage_sources=request.initial_version.lineage_sources,
                    )
                    if request.initial_version is not None
                    else None
                ),
            )
        )
    )
    return ArtifactBundleResponse(artifact=artifact, main_branch=branch)


@router.post(
    "/artifact-branches/{branch_id}/versions",
    response_model=ArtifactVersion,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def create_artifact_version(
    branch_id: UUID,
    request: CreateVersionRequest,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersion:
    branch = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_branch(branch_id)),
    )
    version, _ = _invoke(
        lambda: service.create_version(
            VersionCreateCommand(
                branch_id=branch.id,
                expected_head_version_id=request.expected_head_version_id,
                content_hash=request.content_hash,
                files=request.files,
                provenance=request.provenance,
                rights=request.rights,
                created_by_type=request.created_by_type,
                created_by_id=request.created_by_id,
                created_at=_now(),
                primary_file_id=request.primary_file_id,
                design_document_version_id=request.design_document_version_id,
                quality_score=request.quality_score,
                constraint_snapshot_hash=request.constraint_snapshot_hash,
                lineage_sources=request.lineage_sources,
            )
        )
    )
    return _scope(organization_id, version)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=Artifact,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def get_artifact(
    artifact_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> Artifact:
    return _scope(
        organization_id,
        _invoke(lambda: service.repository.get_artifact(artifact_id)),
    )


@router.get(
    "/artifacts/{artifact_id}/versions",
    response_model=list[ArtifactVersion],
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def list_artifact_versions(
    artifact_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> list[ArtifactVersion]:
    artifact = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_artifact(artifact_id)),
    )
    return list(_invoke(lambda: service.repository.list_versions(artifact.id)))


@router.get(
    "/artifact-versions/{version_id}",
    response_model=ArtifactVersion,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def get_artifact_version(
    version_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersion:
    return _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )


@router.get(
    "/artifact-versions/{version_id}/lineage",
    response_model=list[LineageEdge],
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def get_artifact_lineage(
    version_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> list[LineageEdge]:
    version = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    return list(_invoke(lambda: service.repository.list_lineage(version.id)))


@router.post(
    "/artifact-versions/{version_id}/fork",
    response_model=ArtifactBranch,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def fork_artifact_version(
    version_id: UUID,
    request: ForkVersionRequest,
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
                name=request.name,
                created_by_type=request.created_by_type,
                created_by_id=request.created_by_id,
                created_at=_now(),
            )
        ),
    )


@router.post(
    "/artifact-versions/{version_id}/restore",
    response_model=ArtifactVersion,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def restore_artifact_version(
    version_id: UUID,
    request: RestoreVersionRequest,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersion:
    source = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    target = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_branch(request.target_branch_id)),
    )
    restored, _ = _invoke(
        lambda: service.restore_version(
            source.id,
            target_branch_id=target.id,
            expected_head_version_id=request.expected_head_version_id,
            provenance=request.provenance,
            created_by_type=request.created_by_type,
            created_by_id=request.created_by_id,
            created_at=_now(),
        )
    )
    return _scope(organization_id, restored)


@router.post(
    "/artifact-versions/{version_id}/ready",
    response_model=ArtifactVersion,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def mark_artifact_version_ready(
    version_id: UUID,
    request: MarkReadyRequest,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersion:
    current = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    return _scope(
        organization_id,
        _invoke(lambda: service.mark_ready(current.id, occurred_at=request.occurred_at or _now())),
    )


@router.post(
    "/artifact-versions/{version_id}/approve",
    response_model=ArtifactVersion,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def approve_artifact_version(
    version_id: UUID,
    request: ApproveVersionRequest,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactVersion:
    current = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(version_id)),
    )
    approved, _ = _invoke(
        lambda: service.approve_version(
            current.id,
            approved_by_id=request.approved_by_id,
            approved_at=_now(),
            validation_ref=request.validation_ref,
        )
    )
    return _scope(organization_id, approved)


@router.get(
    "/artifact-versions/{left_id}/compare/{right_id}",
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
def compare_artifact_versions(
    left_id: UUID,
    right_id: UUID,
    organization_id: OrganizationId,
    service: ArtifactEngineServiceDependency,
) -> ArtifactCompareResult:
    left = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(left_id)),
    )
    right = _scope(
        organization_id,
        _invoke(lambda: service.repository.get_version(right_id)),
    )
    return _invoke(lambda: service.compare_versions(left.id, right.id))
