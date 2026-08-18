from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status
from lumi_export_engine import (
    ExportFormat,
    ExportJob,
    ExportOperationConflict,
    ExportRequestItem,
    ExportTaskSpec,
)

from .common import ProblemDetail
from .dependencies import ApiServiceDependency
from .errors import ApiProblem
from .export_product_dependencies import ExportEngineDependency
from .export_product_schemas import (
    CreateExportJobRequest,
    ExportCapabilitiesResponse,
    ExportDownloadGrantResponse,
    ExportFormatCapability,
    ExportJobItemResponse,
    ExportJobResponse,
    ExportManifestEntryResponse,
    ExportManifestResponse,
    ExportOutputResponse,
    ExportPackageResponse,
)
from .headers import IdempotencyKey, OrganizationId

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}

_MIME_FORMAT = {
    "image/png": (ExportFormat.PNG, "PNG", "png"),
    "image/jpeg": (ExportFormat.JPEG, "JPEG", "jpg"),
    "video/mp4": (ExportFormat.MP4, "MP4", "mp4"),
    "application/pdf": (ExportFormat.PDF, "PDF", "pdf"),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        ExportFormat.PPTX,
        "PowerPoint",
        "pptx",
    ),
}


def _actor_id(request: Request) -> str:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Export creation and download signing require an authenticated actor.",
        )
    return str(actor_id)


def _operation_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="export_idempotency_key_must_be_uuid",
            title="Invalid export operation id",
            detail="Export Idempotency-Key must be a UUID.",
        ) from exc


def _problem(exc: Exception) -> ApiProblem:
    code = str(exc) or type(exc).__name__
    if isinstance(exc, KeyError):
        return ApiProblem(status=404, code="export_not_found", title="Export resource not found", detail=code)
    if isinstance(exc, ExportOperationConflict):
        return ApiProblem(status=409, code="export_operation_conflict", title="Export operation conflict", detail=code)
    if isinstance(exc, ValueError):
        if code in {"EXPORT_ARTIFACT_VERSION_NOT_APPROVED", "EXPORT_RIGHTS_REJECTED"}:
            return ApiProblem(status=409, code=code.lower(), title="Artifact cannot be exported", detail=code)
        if code == "EXPORT_PACKAGE_NOT_READY":
            return ApiProblem(status=409, code="export_package_not_ready", title="Export package not ready", detail=code)
        if code in {"EXPORT_FORMAT_NOT_SUPPORTED", "EXPORT_TRANSCODER_REQUIRED"}:
            return ApiProblem(status=422, code=code.lower(), title="Export format unavailable", detail=code)
        return ApiProblem(status=422, code="export_request_invalid", title="Invalid export request", detail=code)
    raise exc


def _capabilities(engine, *, organization_id: UUID, project_id: UUID, version_id: UUID, actor_id: str) -> ExportCapabilitiesResponse:
    try:
        snapshot = engine.snapshots.snapshot_exact(
            organization_id=str(organization_id),
            project_id=str(project_id),
            artifact_version_id=str(version_id),
        )
        engine.authorization.authorize_snapshot(actor_id=actor_id, snapshot=snapshot)
        source = snapshot.primary_file()
    except (KeyError, ValueError, PermissionError) as exc:
        if isinstance(exc, PermissionError):
            raise ApiProblem(status=403, code="export_forbidden", title="Export forbidden", detail="The actor cannot export this artifact version.") from exc
        raise _problem(exc) from exc

    formats = [
        ExportFormatCapability(
            format=ExportFormat.ORIGINAL,
            label="Original file",
            output_extension=_MIME_FORMAT.get(source.mime_type, (ExportFormat.ORIGINAL, "Original", "bin"))[2],
            copy_through=True,
        )
    ]
    matching = _MIME_FORMAT.get(source.mime_type)
    if matching is not None:
        target_format, label, extension = matching
        if any(renderer.supports(artifact_type=snapshot.artifact_type, target_format=target_format) for renderer in engine.renderers):
            formats.append(
                ExportFormatCapability(
                    format=target_format,
                    label=label,
                    output_extension=extension,
                    copy_through=True,
                )
            )
    return ExportCapabilitiesResponse(
        artifact_version_id=version_id,
        approved=True,
        source_mime_type=source.mime_type,
        formats=tuple(formats),
    )


def _job_response(job: ExportJob) -> ExportJobResponse:
    package = None
    manifest = None
    if job.package is not None:
        package = ExportPackageResponse(
            package_id=UUID(job.package.package_id),
            filename=job.package.filename,
            mime_type=job.package.mime_type,
            size_bytes=job.package.size_bytes,
            checksum_sha256=job.package.checksum_sha256,
            is_archive=job.package.is_archive,
        )
        manifest = ExportManifestResponse(
            schema_version=job.package.manifest.schema_version,
            export_job_id=UUID(job.package.manifest.export_job_id),
            operation_id=UUID(job.package.manifest.operation_id),
            created_at=job.package.manifest.created_at,
            exporter_version=job.package.manifest.exporter_version,
            entries=tuple(
                ExportManifestEntryResponse(
                    name=item.name,
                    mime_type=item.mime_type,
                    size_bytes=item.size_bytes,
                    checksum_sha256=item.checksum_sha256,
                    artifact_id=UUID(item.artifact_id),
                    artifact_version_id=UUID(item.artifact_version_id),
                    renderer_version=item.renderer_version,
                )
                for item in job.package.manifest.entries
            ),
        )
    return ExportJobResponse(
        job_id=UUID(job.job_id),
        project_id=UUID(job.spec.project_id),
        task_id=UUID(job.spec.task_id),
        operation_id=UUID(job.spec.operation_id),
        status=job.status,
        items=tuple(
            ExportJobItemResponse(
                artifact_version_id=UUID(item.request.artifact_version_id),
                target_format=item.request.target_format,
                output_name=item.request.output_name,
            )
            for item in job.items
        ),
        outputs=tuple(
            ExportOutputResponse(
                name=item.name,
                mime_type=item.mime_type,
                size_bytes=item.size_bytes,
                checksum_sha256=item.checksum_sha256,
                renderer_version=item.renderer_version,
                source_artifact_id=UUID(item.source_artifact_id),
                source_artifact_version_id=UUID(item.source_artifact_version_id),
            )
            for item in job.outputs
        ),
        package=package,
        manifest=manifest,
        error_code=job.error_code,
    )


def _scoped_job(engine, organization_id: UUID, job_id: UUID) -> ExportJob:
    try:
        job = engine.repository.get(str(job_id))
    except (KeyError, ValueError) as exc:
        raise _problem(exc) from exc
    if job.spec.organization_id != str(organization_id):
        raise ApiProblem(status=404, code="export_not_found", title="Export resource not found", detail="The export job is unavailable in this organization.")
    return job


@router.get(
    "/projects/{project_id}/artifact-versions/{version_id}/export-capabilities",
    response_model=ExportCapabilitiesResponse,
    responses=_ERROR_RESPONSES,
    tags=["exports"],
)
def get_export_capabilities(
    project_id: UUID,
    version_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    engine: ExportEngineDependency,
) -> ExportCapabilitiesResponse:
    return _capabilities(
        engine,
        organization_id=organization_id,
        project_id=project_id,
        version_id=version_id,
        actor_id=_actor_id(request),
    )


@router.post(
    "/projects/{project_id}/export-jobs",
    response_model=ExportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["exports"],
)
async def create_export_job(
    project_id: UUID,
    body: CreateExportJobRequest,
    request: Request,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    engine: ExportEngineDependency,
    api_service: ApiServiceDependency,
) -> ExportJobResponse:
    actor_id = _actor_id(request)
    task = await api_service.get_task(organization_id, body.task_id)
    if task.project_id != project_id:
        raise ApiProblem(status=409, code="export_task_project_mismatch", title="Export task mismatch", detail="The export task does not belong to this project.")

    items: list[ExportRequestItem] = []
    for item in body.items:
        capabilities = _capabilities(
            engine,
            organization_id=organization_id,
            project_id=project_id,
            version_id=item.artifact_version_id,
            actor_id=actor_id,
        )
        allowed = {entry.format for entry in capabilities.formats}
        if item.target_format not in allowed:
            raise ApiProblem(status=422, code="export_format_not_available_for_version", title="Export format unavailable", detail=f"{item.target_format.value} is not supported for this exact ArtifactVersion.")
        items.append(
            ExportRequestItem(
                artifact_version_id=str(item.artifact_version_id),
                target_format=item.target_format,
                output_name=item.output_name.strip(),
            )
        )

    try:
        job = engine.create(
            ExportTaskSpec(
                organization_id=str(organization_id),
                project_id=str(project_id),
                task_id=str(body.task_id),
                operation_id=_operation_id(idempotency_key),
                requested_by=actor_id,
                items=tuple(items),
                force_zip=body.force_zip,
                package_name=body.package_name.strip(),
            )
        )
    except (KeyError, ValueError, ExportOperationConflict) as exc:
        raise _problem(exc) from exc
    return _job_response(job)


@router.get(
    "/export-jobs/{job_id}",
    response_model=ExportJobResponse,
    responses=_ERROR_RESPONSES,
    tags=["exports"],
)
def get_export_job(
    job_id: UUID,
    organization_id: OrganizationId,
    engine: ExportEngineDependency,
) -> ExportJobResponse:
    return _job_response(_scoped_job(engine, organization_id, job_id))


@router.post(
    "/export-jobs/{job_id}/cancel",
    response_model=ExportJobResponse,
    responses=_ERROR_RESPONSES,
    tags=["exports"],
)
def cancel_export_job(
    job_id: UUID,
    organization_id: OrganizationId,
    engine: ExportEngineDependency,
) -> ExportJobResponse:
    _scoped_job(engine, organization_id, job_id)
    try:
        return _job_response(engine.cancel(str(job_id)))
    except (KeyError, ValueError) as exc:
        raise _problem(exc) from exc


@router.post(
    "/export-jobs/{job_id}/download-grants",
    response_model=ExportDownloadGrantResponse,
    responses=_ERROR_RESPONSES,
    tags=["exports"],
)
async def issue_export_download_grant(
    job_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    engine: ExportEngineDependency,
) -> ExportDownloadGrantResponse:
    job = _scoped_job(engine, organization_id, job_id)
    try:
        grant = await engine.issue_download(str(job_id), actor_id=_actor_id(request))
    except (KeyError, ValueError, PermissionError) as exc:
        if isinstance(exc, PermissionError):
            raise ApiProblem(status=403, code="export_download_forbidden", title="Download forbidden", detail="The actor cannot download this export package.") from exc
        raise _problem(exc) from exc
    if job.package is None:
        raise ApiProblem(status=409, code="export_package_not_ready", title="Export package not ready", detail="The export package is not available yet.")
    return ExportDownloadGrantResponse(
        job_id=job_id,
        package_id=UUID(grant.package_id),
        filename=job.package.filename,
        mime_type=job.package.mime_type,
        size_bytes=job.package.size_bytes,
        checksum_sha256=job.package.checksum_sha256,
        expires_at=grant.expires_at,
        url=grant.url,
    )
