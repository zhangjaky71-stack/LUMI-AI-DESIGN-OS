from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_asset_storage.s3 import S3ObjectStore
from lumi_domain.job_dispatch import JobDispatch
from lumi_image_generation.model import ImageGenerationSpec, OutputRequirements
from lumi_image_generation.spec_codec import encode_spec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.auth.principal import PrincipalResolver
from lumi_api.auth.service import AuthService
from lumi_api.persistence.models import (
    ArtifactFile,
    ArtifactProvenance,
    ArtifactVersion,
    Generation,
    Organization,
    OrganizationMember,
    OutboxEvent,
    Project,
    Task,
    User,
    Workspace,
)
from lumi_api.persistence.session import create_engine, create_session_factory

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_JOB_KIND = "image.transform"
_OUTBOX_EVENT = "job.dispatch.requested"
_TASK_NAME = "lumi.jobs.image.transform"
_QUEUE = "lumi.media.image"
_EVIDENCE_MAX_BYTES = 1024 * 1024
_API_PORT = 8000


class CollectorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScopeIds:
    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    workspace_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID


def _required_env(name: str, *, max_length: int = 2048) -> str:
    value = os.getenv(name, "").strip()
    if not value or len(value) > max_length or "\x00" in value:
        raise CollectorError(f"{name}_REQUIRED")
    return value


def _release_sha() -> str:
    value = _required_env("LUMI_E2E_RELEASE_GIT_SHA", max_length=40).lower()
    if not _SHA40.fullmatch(value):
        raise CollectorError("LUMI_E2E_RELEASE_GIT_SHA_INVALID")
    return value


def _run_id() -> str:
    raw = _required_env("LUMI_E2E_RUN_ID", max_length=80)
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.")
    if not normalized or len(normalized) > 80:
        raise CollectorError("LUMI_E2E_RUN_ID_INVALID")
    return normalized


def _timeout_seconds() -> int:
    raw = os.getenv("LUMI_E2E_TIMEOUT_SECONDS", "900").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise CollectorError("LUMI_E2E_TIMEOUT_SECONDS_INVALID") from exc
    if not 60 <= value <= 1800:
        raise CollectorError("LUMI_E2E_TIMEOUT_SECONDS_OUT_OF_RANGE")
    return value


def _region() -> str:
    value = (
        os.getenv("LUMI_E2E_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or ""
    ).strip()
    if not value or len(value) > 64 or "\x00" in value:
        raise CollectorError("LUMI_E2E_AWS_REGION_REQUIRED")
    return value


def _api_base_url() -> str:
    environment = os.getenv("LUMI_ENV", "").strip().casefold()
    if environment != "staging":
        raise CollectorError("E2E_COLLECTOR_STAGING_ONLY")
    return f"http://api.{environment}.lumi.internal:{_API_PORT}"


def _scope_ids(release_sha: str, run_id: str) -> ScopeIds:
    root = f"https://lumi.invalid/node73/e2e-03/{release_sha}/{run_id}"
    return ScopeIds(
        user_id=uuid5(NAMESPACE_URL, f"{root}/user"),
        organization_id=uuid5(NAMESPACE_URL, f"{root}/organization"),
        membership_id=uuid5(NAMESPACE_URL, f"{root}/membership"),
        workspace_id=uuid5(NAMESPACE_URL, f"{root}/workspace"),
        project_id=uuid5(NAMESPACE_URL, f"{root}/project"),
        task_id=uuid5(NAMESPACE_URL, f"{root}/task"),
        operation_id=uuid5(NAMESPACE_URL, f"{root}/operation"),
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _snapshot(stage_ref: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": stage_ref,
        "sha256": hashlib.sha256(_canonical_json(value)).hexdigest(),
        "snapshot": value,
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


async def _ensure_synthetic_scope(
    factory: async_sessionmaker[AsyncSession],
    *,
    ids: ScopeIds,
    run_id: str,
) -> None:
    email = f"node73-e2e-{run_id}@lumi.invalid".lower()
    slug_suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    organization_slug = f"node73-e2e-{slug_suffix}"
    async with factory() as session, session.begin():
        user = await session.get(User, ids.user_id)
        if user is None:
            session.add(
                User(
                    id=ids.user_id,
                    email=email,
                    display_name=f"NODE-73 E2E {run_id}",
                    status="active",
                    email_verified_at=datetime.now(UTC),
                )
            )
        elif user.email != email or user.status != "active":
            raise CollectorError("E2E_SYNTHETIC_USER_CONFLICT")

        organization = await session.get(Organization, ids.organization_id)
        if organization is None:
            session.add(
                Organization(
                    id=ids.organization_id,
                    name=f"NODE-73 E2E {run_id}",
                    slug=organization_slug,
                    status="active",
                    plan="development",
                    settings_json={"synthetic_only": True, "acceptance_scenario": "E2E-03"},
                )
            )
        elif organization.slug != organization_slug or organization.status != "active":
            raise CollectorError("E2E_SYNTHETIC_ORGANIZATION_CONFLICT")

        membership = await session.get(OrganizationMember, ids.membership_id)
        if membership is None:
            session.add(
                OrganizationMember(
                    id=ids.membership_id,
                    organization_id=ids.organization_id,
                    user_id=ids.user_id,
                    role="OWNER",
                    status="active",
                )
            )
        elif (
            membership.organization_id != ids.organization_id
            or membership.user_id != ids.user_id
            or membership.role != "OWNER"
            or membership.status != "active"
        ):
            raise CollectorError("E2E_SYNTHETIC_MEMBERSHIP_CONFLICT")

        workspace = await session.get(Workspace, ids.workspace_id)
        if workspace is None:
            session.add(
                Workspace(
                    id=ids.workspace_id,
                    organization_id=ids.organization_id,
                    name="NODE-73 E2E Workspace",
                    slug="e2e",
                    settings_json={"synthetic_only": True},
                )
            )
        elif workspace.organization_id != ids.organization_id:
            raise CollectorError("E2E_SYNTHETIC_WORKSPACE_CONFLICT")

        project = await session.get(Project, ids.project_id)
        if project is None:
            session.add(
                Project(
                    id=ids.project_id,
                    organization_id=ids.organization_id,
                    workspace_id=ids.workspace_id,
                    name="NODE-73 Media Generation E2E",
                    status="active",
                    brief_json={
                        "schema_version": "1.0",
                        "objective": "Synthetic release acceptance image generation",
                        "audience": ["release-validation"],
                        "synthetic_only": True,
                    },
                    brief_version=1,
                    settings_json={"synthetic_only": True, "acceptance_scenario": "E2E-03"},
                    created_by=ids.user_id,
                )
            )
        elif (
            project.organization_id != ids.organization_id
            or project.workspace_id != ids.workspace_id
            or project.status != "active"
        ):
            raise CollectorError("E2E_SYNTHETIC_PROJECT_CONFLICT")
        await session.flush()


async def _issue_token(
    factory: async_sessionmaker[AsyncSession],
    *,
    ids: ScopeIds,
    run_id: str,
) -> tuple[UUID, str]:
    async with factory() as session, session.begin():
        result = await AuthService(session).create_api_token(
            actor_id=ids.user_id,
            organization_id=ids.organization_id,
            name=f"NODE-73 E2E {run_id}",
            scopes=frozenset({"project.read", "project.write"}),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        return result.token_id, result.plaintext


async def _revoke_token(
    factory: async_sessionmaker[AsyncSession],
    *,
    ids: ScopeIds,
    token_id: UUID,
) -> None:
    async with factory() as session, session.begin():
        await PrincipalResolver(session).revoke_api_token(
            actor_id=ids.user_id,
            organization_id=ids.organization_id,
            token_id=token_id,
            now=datetime.now(UTC),
        )


def _http_json_sync(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    expected_status: int,
) -> tuple[dict[str, Any], dict[str, str]]:
    body = _canonical_json(payload) if payload is not None else None
    request = Request(url=url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed internal staging host
            status = int(response.status)
            raw = response.read(1024 * 1024)
            response_headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CollectorError(f"E2E_HTTP_{exc.code}:{detail[:1000]}") from exc
    except URLError as exc:
        raise CollectorError(f"E2E_HTTP_UNAVAILABLE:{type(exc.reason).__name__}") from exc
    if status != expected_status:
        raise CollectorError(f"E2E_HTTP_STATUS_EXPECTED_{expected_status}_GOT_{status}")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CollectorError("E2E_HTTP_RESPONSE_JSON_INVALID") from exc
    if not isinstance(decoded, dict):
        raise CollectorError("E2E_HTTP_RESPONSE_OBJECT_REQUIRED")
    return decoded, response_headers


async def _http_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, str]]:
    return await asyncio.to_thread(_http_json_sync, **kwargs)


def _resource(envelope: dict[str, Any], *, name: str) -> dict[str, Any]:
    value = envelope.get("data")
    if not isinstance(value, dict):
        raise CollectorError(f"E2E_{name}_RESOURCE_MISSING")
    return value


def _generation_spec(*, ids: ScopeIds, release_sha: str, run_id: str) -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=str(ids.organization_id),
        project_id=str(ids.project_id),
        task_id=str(ids.task_id),
        operation_id=str(ids.operation_id),
        purpose="NODE-73 E2E-03 Production-like Staging release acceptance",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref=f"staging-e2e://node73/{run_id}",
        objective="Generate one synthetic release-validation image.",
        content="A neutral matte white geometric object on a soft gray studio background; no text, logos, people, or brands.",
        visual_direction="minimal neutral product-studio lighting",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="DRAFT",
        budget_limit_usd=Decimal("2.00"),
        output_requirements=OutputRequirements(format="PNG", exact_dimensions=True),
        code_git_sha=release_sha,
        skill_versions={"acceptance": "node73-e2e-03-v1"},
        seed=73,
        user_intent_ref=f"synthetic://node73/{run_id}",
    )


async def _create_generation_via_api(
    *,
    ids: ScopeIds,
    release_sha: str,
    run_id: str,
    token: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], str, str]:
    base_url = _api_base_url()
    trace_id = f"node73-e2e-trace-{run_id}"
    request_id = f"node73-e2e-request-{run_id}"
    spec = _generation_spec(ids=ids, release_sha=release_sha, run_id=run_id)
    payload = {
        "project_id": str(ids.project_id),
        "capability": "image.generate",
        "request": encode_spec(spec),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"node73-e2e-{release_sha}-{run_id}",
        "X-Lumi-Organization-Id": str(ids.organization_id),
        "X-Request-Id": request_id,
        "X-Trace-Id": trace_id,
    }
    response, response_headers = await _http_json(
        method="POST",
        url=f"{base_url}/api/v1/generations",
        headers=headers,
        payload=payload,
        expected_status=202,
    )
    resource = _resource(response, name="GENERATION_CREATE")
    if resource.get("task_id") != str(ids.task_id):
        raise CollectorError("E2E_GENERATION_TASK_ID_MISMATCH")
    if resource.get("operation_id") != str(ids.operation_id):
        raise CollectorError("E2E_GENERATION_OPERATION_ID_MISMATCH")
    response_request_id = response_headers.get("x-request-id", "")
    if response_request_id != request_id:
        raise CollectorError("E2E_GENERATION_REQUEST_ID_MISMATCH")
    api_snapshot = {
        "method": "POST",
        "path": "/api/v1/generations",
        "status_code": 202,
        "request_id": request_id,
        "trace_id": trace_id,
        "organization_id": str(ids.organization_id),
        "project_id": str(ids.project_id),
        "capability": "image.generate",
        "task_id": str(ids.task_id),
        "operation_id": str(ids.operation_id),
        "generation_id": str(resource.get("id")),
    }
    return resource, response_headers, api_snapshot, request_id, trace_id


async def _poll_terminal(
    *,
    ids: ScopeIds,
    generation_id: UUID,
    token: str,
    request_id: str,
    trace_id: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_url = _api_base_url()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Lumi-Organization-Id": str(ids.organization_id),
        "X-Request-Id": request_id,
        "X-Trace-Id": trace_id,
    }
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_generation: dict[str, Any] = {}
    last_task: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < deadline:
        generation_envelope, _ = await _http_json(
            method="GET",
            url=f"{base_url}/api/v1/generations/{generation_id}",
            headers=headers,
            payload=None,
            expected_status=200,
        )
        task_envelope, _ = await _http_json(
            method="GET",
            url=f"{base_url}/api/v1/tasks/{ids.task_id}",
            headers=headers,
            payload=None,
            expected_status=200,
        )
        last_generation = _resource(generation_envelope, name="GENERATION_GET")
        last_task = _resource(task_envelope, name="TASK_GET")
        generation_status = str(last_generation.get("status", "")).casefold()
        task_status = str(last_task.get("status", "")).casefold()
        if generation_status == "completed" and task_status == "succeeded":
            return last_generation, last_task
        if generation_status in {"failed", "partial"}:
            raise CollectorError(f"E2E_GENERATION_TERMINAL_{generation_status.upper()}")
        if task_status in {"failed", "cancelled"}:
            raise CollectorError(f"E2E_TASK_TERMINAL_{task_status.upper()}")
        await asyncio.sleep(5)
    raise CollectorError(
        "E2E_TERMINAL_TIMEOUT:"
        f"generation={last_generation.get('status')}:task={last_task.get('status')}"
    )


def _first_ready_artifact(task: Task) -> tuple[UUID, UUID]:
    output = dict(task.output_json or {})
    artifacts = output.get("artifacts")
    if not isinstance(artifacts, list):
        raise CollectorError("E2E_WORKER_ARTIFACT_LIST_MISSING")
    for raw in artifacts:
        if not isinstance(raw, dict) or str(raw.get("status", "")).upper() != "READY":
            continue
        try:
            return UUID(str(raw["artifact_id"])), UUID(str(raw["artifact_version_id"]))
        except (KeyError, ValueError) as exc:
            raise CollectorError("E2E_WORKER_ARTIFACT_ID_INVALID") from exc
    raise CollectorError("E2E_WORKER_READY_ARTIFACT_MISSING")


async def _collect_database_evidence(
    factory: async_sessionmaker[AsyncSession],
    *,
    ids: ScopeIds,
    generation_id: UUID,
    release_sha: str,
    evidence_uri: str,
    s3: S3ObjectStore,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    expected_outbox_id = uuid5(ids.operation_id, f"lumi:image-transform-dispatch:{ids.task_id}")
    async with factory() as session:
        generation = await session.scalar(
            select(Generation).where(
                Generation.id == generation_id,
                Generation.organization_id == ids.organization_id,
                Generation.project_id == ids.project_id,
            )
        )
        task = await session.scalar(
            select(Task).where(
                Task.id == ids.task_id,
                Task.organization_id == ids.organization_id,
                Task.project_id == ids.project_id,
            )
        )
        outbox = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.id == expected_outbox_id,
                OutboxEvent.organization_id == ids.organization_id,
            )
        )
        if generation is None or task is None or outbox is None:
            raise CollectorError("E2E_CANONICAL_ROWS_MISSING")
        if generation.status != "completed":
            raise CollectorError(f"E2E_GENERATION_DB_STATUS:{generation.status}")
        if task.status != "succeeded":
            raise CollectorError(f"E2E_TASK_DB_STATUS:{task.status}")
        if generation.task_id != ids.task_id or generation.operation_id != ids.operation_id:
            raise CollectorError("E2E_GENERATION_DB_SCOPE_MISMATCH")
        if task.type != _JOB_KIND:
            raise CollectorError("E2E_TASK_DB_TYPE_MISMATCH")

        dispatch = JobDispatch.from_outbox_payload(dict(outbox.payload_json or {}))
        if dispatch.task_name != _TASK_NAME or dispatch.queue != _QUEUE:
            raise CollectorError("E2E_OUTBOX_DISPATCH_ROUTE_MISMATCH")
        if dispatch.message.job_id != ids.task_id or dispatch.message.operation_id != ids.operation_id:
            raise CollectorError("E2E_OUTBOX_MESSAGE_SCOPE_MISMATCH")

        artifact_id, artifact_version_id = _first_ready_artifact(task)
        version = await session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.id == artifact_version_id,
                ArtifactVersion.organization_id == ids.organization_id,
                ArtifactVersion.artifact_id == artifact_id,
            )
        )
        file_rows = (
            await session.scalars(
                select(ArtifactFile).where(
                    ArtifactFile.organization_id == ids.organization_id,
                    ArtifactFile.artifact_version_id == artifact_version_id,
                )
            )
        ).all()
        provenance_rows = (
            await session.scalars(
                select(ArtifactProvenance).where(
                    ArtifactProvenance.organization_id == ids.organization_id,
                    ArtifactProvenance.artifact_version_id == artifact_version_id,
                    ArtifactProvenance.source_type == "generation",
                    ArtifactProvenance.source_id == ids.operation_id,
                )
            )
        ).all()
        if version is None or version.status != "ready":
            raise CollectorError("E2E_ARTIFACT_VERSION_NOT_READY")
        if len(file_rows) != 1:
            raise CollectorError("E2E_ARTIFACT_FILE_CARDINALITY")
        if len(provenance_rows) != 1:
            raise CollectorError("E2E_ARTIFACT_PROVENANCE_CARDINALITY")
        file_row = file_rows[0]
        provenance = provenance_rows[0]
        metadata = dict(provenance.metadata_json or {})
        code_git_sha = str(metadata.get("code_git_sha", "")).casefold()
        if code_git_sha != release_sha:
            raise CollectorError("E2E_PROVENANCE_RELEASE_SHA_MISMATCH")

        object_head = await s3.head(bucket=file_row.bucket, object_key=file_row.object_key)
        if object_head.content_length <= 0:
            raise CollectorError("E2E_GENERATED_OBJECT_EMPTY")
        if object_head.content_type != file_row.mime_type:
            raise CollectorError("E2E_GENERATED_OBJECT_MIME_MISMATCH")

        broker_message = dispatch.message.as_dict()
        if any(value is None for value in broker_message.values()):
            raise CollectorError("E2E_BROKER_MESSAGE_IDENTIFIER_MISSING")

        stage_values: dict[str, dict[str, Any]] = {
            "generation_row": {
                "id": str(generation.id),
                "organization_id": str(generation.organization_id),
                "project_id": str(generation.project_id),
                "task_id": str(generation.task_id),
                "operation_id": str(generation.operation_id),
                "capability": generation.capability,
                "provider": generation.provider,
                "model": generation.model,
                "status": generation.status,
                "created_at": _iso(generation.created_at),
            },
            "task_row": {
                "id": str(task.id),
                "organization_id": str(task.organization_id),
                "project_id": str(task.project_id),
                "type": task.type,
                "status": task.status,
                "attempt_count": task.attempt_count,
                "max_attempts": task.max_attempts,
                "started_at": _iso(task.started_at),
                "finished_at": _iso(task.finished_at),
                "input_schema_version": dict(task.input_json or {}).get("schema_version"),
                "input_job_kind": dict(task.input_json or {}).get("job_kind"),
            },
            "outbox_dispatch": {
                "id": str(outbox.id),
                "event_name": outbox.event_name,
                "aggregate_type": outbox.aggregate_type,
                "aggregate_id": str(outbox.aggregate_id),
                "schema_version": outbox.schema_version,
                "publish_attempts": outbox.publish_attempts,
                "published_at": _iso(getattr(outbox, "published_at", None)),
                "payload": dict(outbox.payload_json or {}),
            },
            "worker_execution": {
                "task_id": str(task.id),
                "attempt_count": task.attempt_count,
                "started_at": _iso(task.started_at),
                "finished_at": _iso(task.finished_at),
                "output": dict(task.output_json or {}),
            },
            "artifact": {
                "artifact_id": str(artifact_id),
                "artifact_version_id": str(artifact_version_id),
                "status": version.status,
                "content_hash": version.content_hash,
                "file": {
                    "format": file_row.format,
                    "bucket": file_row.bucket,
                    "object_key": file_row.object_key,
                    "checksum_sha256": file_row.checksum_sha256,
                    "mime_type": file_row.mime_type,
                    "content_length": object_head.content_length,
                },
            },
            "provenance": {
                "id": str(provenance.id),
                "artifact_version_id": str(provenance.artifact_version_id),
                "source_type": provenance.source_type,
                "source_id": str(provenance.source_id),
                "operation": provenance.operation,
                "generation_id": metadata.get("generation_id"),
                "provider": metadata.get("provider"),
                "model": metadata.get("model"),
                "prompt_hash": metadata.get("prompt_hash"),
                "prompt_template_version": metadata.get("prompt_template_version"),
                "pricing_snapshot_id": metadata.get("pricing_snapshot_id"),
                "cost_usd": metadata.get("cost_usd"),
                "cost_confidence": metadata.get("cost_confidence"),
                "code_git_sha": code_git_sha,
                "recipe_version": metadata.get("recipe_version"),
                "skill_versions": metadata.get("skill_versions") or {},
            },
        }
        refs = {
            name: _snapshot(
                f"{evidence_uri}#/scenario_results/E2E-03/media_generation/evidence/{name}",
                value,
            )
            for name, value in stage_values.items()
        }
        observed = {
            "organization_id": str(ids.organization_id),
            "project_id": str(ids.project_id),
            "task_id": str(ids.task_id),
            "generation_id": str(generation.id),
            "operation_id": str(ids.operation_id),
            "outbox_event_id": str(outbox.id),
            "artifact_id": str(artifact_id),
            "artifact_version_id": str(artifact_version_id),
            "provenance_id": str(provenance.id),
            "job_kind": _JOB_KIND,
            "outbox_event_name": _OUTBOX_EVENT,
            "task_name": _TASK_NAME,
            "queue": _QUEUE,
            "task_status": task.status,
            "generation_status": generation.status,
            "provenance_code_git_sha": code_git_sha,
            "storage_ref": f"s3://{file_row.bucket}/{file_row.object_key}",
            "broker_message": broker_message,
        }
        return observed, refs


async def _write_evidence(
    *,
    s3: S3ObjectStore,
    bucket: str,
    key: str,
    evidence: dict[str, Any],
    release_sha: str,
    run_id: str,
) -> str:
    data = _canonical_json(evidence)
    await s3.put_bytes(
        bucket=bucket,
        object_key=key,
        data=data,
        content_type="application/json",
        max_bytes=_EVIDENCE_MAX_BYTES,
        metadata={
            "scenario": "E2E-03",
            "release-git-sha": release_sha,
            "collector-run": run_id,
            "synthetic-only": "true",
        },
    )
    return hashlib.sha256(data).hexdigest()


async def run() -> dict[str, str]:
    release_sha = _release_sha()
    run_id = _run_id()
    timeout_seconds = _timeout_seconds()
    evidence_bucket = _required_env("LUMI_E2E_EVIDENCE_BUCKET", max_length=255)
    evidence_key = _required_env("LUMI_E2E_EVIDENCE_KEY", max_length=1024)
    if not evidence_key.startswith("acceptance/node73/e2e-03/") or not evidence_key.endswith(".json"):
        raise CollectorError("LUMI_E2E_EVIDENCE_KEY_OUTSIDE_ACCEPTANCE_PREFIX")
    region = _region()
    evidence_uri = f"s3://{evidence_bucket}/{evidence_key}"
    ids = _scope_ids(release_sha, run_id)
    engine = create_engine()
    factory = create_session_factory(engine)
    s3 = S3ObjectStore(
        endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL"),
        region_name=region,
        access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID"),
        secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY"),
        force_path_style=os.getenv("LUMI_S3_FORCE_PATH_STYLE", "").strip().casefold()
        in {"1", "true", "yes", "on"},
    )
    token_id: UUID | None = None
    try:
        await _ensure_synthetic_scope(factory, ids=ids, run_id=run_id)
        token_id, token = await _issue_token(factory, ids=ids, run_id=run_id)
        created, _, api_snapshot, request_id, trace_id = await _create_generation_via_api(
            ids=ids,
            release_sha=release_sha,
            run_id=run_id,
            token=token,
        )
        try:
            generation_id = UUID(str(created["id"]))
        except (KeyError, ValueError) as exc:
            raise CollectorError("E2E_GENERATION_ID_INVALID") from exc
        await _poll_terminal(
            ids=ids,
            generation_id=generation_id,
            token=token,
            request_id=request_id,
            trace_id=trace_id,
            timeout_seconds=timeout_seconds,
        )
        observed, stages = await _collect_database_evidence(
            factory,
            ids=ids,
            generation_id=generation_id,
            release_sha=release_sha,
            evidence_uri=evidence_uri,
            s3=s3,
        )
        stages["api_request"] = _snapshot(
            f"{evidence_uri}#/scenario_results/E2E-03/media_generation/evidence/api_request",
            api_snapshot,
        )
        observed["request_id"] = request_id
        observed["trace_id"] = trace_id
        observed["evidence"] = stages
        evidence = {
            "schema_version": 1,
            "collected_at": datetime.now(UTC).isoformat(),
            "collector": {
                "environment": "staging",
                "run_id": run_id,
                "synthetic_only": True,
                "transport": "deployed-api-http-plus-canonical-durable-state",
            },
            "release_candidate": {"git_sha": release_sha},
            "scenario_results": {
                "E2E-03": {
                    "status": "PASS",
                    "actual": "Synthetic request traversed deployed API, canonical outbox, Worker Media, durable generated S3 object, artifact, and provenance.",
                    "evidence_ref": evidence_uri,
                    "owner": "release-engineering",
                    "media_generation": observed,
                }
            },
        }
        evidence_sha256 = await _write_evidence(
            s3=s3,
            bucket=evidence_bucket,
            key=evidence_key,
            evidence=evidence,
            release_sha=release_sha,
            run_id=run_id,
        )
        return {
            "status": "PASS",
            "scenario_id": "E2E-03",
            "evidence_uri": evidence_uri,
            "evidence_sha256": evidence_sha256,
            "generation_id": str(generation_id),
            "task_id": str(ids.task_id),
            "operation_id": str(ids.operation_id),
        }
    finally:
        if token_id is not None:
            try:
                await _revoke_token(factory, ids=ids, token_id=token_id)
            except Exception as exc:
                raise CollectorError("E2E_API_TOKEN_REVOCATION_FAILED") from exc
        await engine.dispose()


def main() -> int:
    try:
        result = asyncio.run(run())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "scenario_id": "E2E-03",
                    "error": str(exc)[:1000],
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
