from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.persistence.models import (
    Artifact,
    ArtifactFile,
    ArtifactVersion,
    Asset,
    AssetFile,
    Project,
    Task,
)

_MAX_BODY_BYTES = 512 * 1024
_MAX_SKEW_SECONDS = 90
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_SERVICE_HEADER = "X-Lumi-Service"
_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_SIGNATURE_HEADER = "X-Lumi-Signature"
_PROJECT_SUMMARY_QUERY = "project.summary"


class ToolDataStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def query_project(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        query: str,
    ) -> dict[str, Any]:
        if query != _PROJECT_SUMMARY_QUERY:
            raise ValueError("TOOL_DATA_PROJECT_QUERY_UNSUPPORTED")
        async with self._session_factory() as session:
            project_id = await self._task_project_id(
                session,
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
            )
            project = await session.scalar(
                select(Project).where(
                    Project.id == project_id,
                    Project.organization_id == organization_id,
                    Project.deleted_at.is_(None),
                )
            )
            if project is None:
                raise KeyError("TOOL_DATA_PROJECT_NOT_FOUND_OR_FORBIDDEN")
            return {
                "project_id": str(project.id),
                "name": project.name,
                "status": project.status,
                "summary": dict(project.brief_json),
            }

    async def read_asset(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        asset_id: UUID,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            project_id = await self._task_project_id(
                session,
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
            )
            asset = await session.scalar(
                select(Asset).where(
                    Asset.id == asset_id,
                    Asset.organization_id == organization_id,
                    Asset.project_id == project_id,
                    Asset.deleted_at.is_(None),
                )
            )
            if asset is None:
                raise KeyError("TOOL_DATA_ASSET_NOT_FOUND_OR_FORBIDDEN")
            files = (
                await session.scalars(
                    select(AssetFile)
                    .where(
                        AssetFile.organization_id == organization_id,
                        AssetFile.asset_id == asset_id,
                    )
                    .order_by(AssetFile.variant.asc())
                )
            ).all()
            return self._asset_payload(asset, files)

    async def inspect_media(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        asset_id: UUID,
    ) -> dict[str, Any]:
        asset = await self.read_asset(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            asset_id=asset_id,
        )
        return {
            "asset_id": asset["asset_id"],
            "kind": asset["kind"],
            "status": asset["status"],
            "files": asset["files"],
            "metadata": asset["metadata"],
        }

    async def query_artifact(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        artifact_id: UUID,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            project_id = await self._task_project_id(
                session,
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
            )
            artifact = await session.scalar(
                select(Artifact).where(
                    Artifact.id == artifact_id,
                    Artifact.organization_id == organization_id,
                    Artifact.project_id == project_id,
                )
            )
            if artifact is None:
                raise KeyError("TOOL_DATA_ARTIFACT_NOT_FOUND_OR_FORBIDDEN")
            version = await session.scalar(
                select(ArtifactVersion)
                .where(
                    ArtifactVersion.organization_id == organization_id,
                    ArtifactVersion.project_id == project_id,
                    ArtifactVersion.artifact_id == artifact_id,
                )
                .order_by(ArtifactVersion.version_number.desc())
                .limit(1)
            )
            version_payload: dict[str, Any] | None = None
            if version is not None:
                files = (
                    await session.scalars(
                        select(ArtifactFile)
                        .where(
                            ArtifactFile.organization_id == organization_id,
                            ArtifactFile.artifact_version_id == version.id,
                        )
                        .order_by(ArtifactFile.format.asc())
                    )
                ).all()
                version_payload = {
                    "version_id": str(version.id),
                    "version_number": version.version_number,
                    "status": version.status,
                    "content_hash": version.content_hash,
                    "quality_score": version.quality_score,
                    "metadata": dict(version.metadata_json),
                    "files": [
                        {
                            "format": item.format,
                            "mime_type": item.mime_type,
                            "checksum_sha256": item.checksum_sha256,
                        }
                        for item in files
                    ],
                }
            return {
                "artifact_id": str(artifact.id),
                "project_id": str(artifact.project_id),
                "kind": artifact.kind,
                "title": artifact.title,
                "metadata": dict(artifact.metadata_json),
                "latest_version": version_payload,
            }

    @staticmethod
    async def _task_project_id(
        session: AsyncSession,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
    ) -> UUID:
        task = await session.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.organization_id == organization_id,
                Task.agent_run_id == agent_run_id,
            )
        )
        if task is None:
            raise KeyError("TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN")
        return task.project_id

    @staticmethod
    def _asset_payload(asset: Asset, files: list[AssetFile]) -> dict[str, Any]:
        return {
            "asset_id": str(asset.id),
            "project_id": str(asset.project_id),
            "kind": asset.kind,
            "source": asset.source,
            "name": asset.original_name,
            "status": asset.status,
            "metadata": dict(asset.metadata_json),
            "files": [
                {
                    "variant": item.variant,
                    "mime_type": item.mime_type,
                    "byte_size": item.byte_size,
                    "width": item.width,
                    "height": item.height,
                    "checksum_sha256": item.checksum_sha256,
                }
                for item in files
            ],
        }


@dataclass(frozen=True, slots=True)
class ToolDataControlRuntime:
    store: ToolDataStore
    auth_secret: str


def build_tool_data_control_runtime(
    session_factory: async_sessionmaker[AsyncSession],
) -> ToolDataControlRuntime:
    secret = os.getenv("LUMI_TOOL_DATA_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_TOOL_DATA_AUTH_SECRET_REQUIRED")
    return ToolDataControlRuntime(
        store=ToolDataStore(session_factory),
        auth_secret=secret,
    )


def create_tool_data_control_router(runtime: ToolDataControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/tool-data", tags=["internal-tool-data"])

    @router.post("/project/query")
    async def project_query(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        try:
            result = await runtime.store.query_project(
                organization_id=UUID(_required_string(payload, "organization_id", 36)),
                agent_run_id=UUID(_required_string(payload, "agent_run_id", 36)),
                task_id=UUID(_required_string(payload, "task_id", 36)),
                query=_required_string(payload, "query", 128),
            )
        except ValueError as exc:
            return _error(422, "TOOL_DATA_QUERY_INVALID", str(exc))
        except KeyError as exc:
            return _error(404, "TOOL_DATA_NOT_FOUND_OR_FORBIDDEN", str(exc))
        except Exception:
            return _error(
                503,
                "TOOL_DATA_CONTROL_UNAVAILABLE",
                "canonical Tool Data control plane is unavailable",
            )
        return JSONResponse(status_code=200, content=result)

    @router.post("/asset/read")
    async def asset_read(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        return await _resource_response(
            runtime.store.read_asset,
            payload,
            resource_key="asset_id",
        )

    @router.post("/artifact/query")
    async def artifact_query(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        return await _resource_response(
            runtime.store.query_artifact,
            payload,
            resource_key="artifact_id",
        )

    @router.post("/media/inspect")
    async def media_inspect(request: Request) -> JSONResponse:
        payload_or_error = await _authenticated_json(request, runtime.auth_secret)
        if isinstance(payload_or_error, JSONResponse):
            return payload_or_error
        payload = payload_or_error
        return await _resource_response(
            runtime.store.inspect_media,
            payload,
            resource_key="asset_id",
        )

    return router


async def _resource_response(
    operation: Any,
    payload: dict[str, Any],
    *,
    resource_key: str,
) -> JSONResponse:
    try:
        result = await operation(
            organization_id=UUID(_required_string(payload, "organization_id", 36)),
            agent_run_id=UUID(_required_string(payload, "agent_run_id", 36)),
            task_id=UUID(_required_string(payload, "task_id", 36)),
            **{resource_key: UUID(_required_string(payload, resource_key, 36))},
        )
    except ValueError as exc:
        return _error(422, "TOOL_DATA_QUERY_INVALID", str(exc))
    except KeyError as exc:
        return _error(404, "TOOL_DATA_NOT_FOUND_OR_FORBIDDEN", str(exc))
    except Exception:
        return _error(
            503,
            "TOOL_DATA_CONTROL_UNAVAILABLE",
            "canonical Tool Data control plane is unavailable",
        )
    return JSONResponse(status_code=200, content=result)


async def _authenticated_json(request: Request, secret: str) -> dict[str, Any] | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(400, "TOOL_DATA_CONTENT_LENGTH_INVALID", "invalid content length")
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(413, "TOOL_DATA_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "TOOL_DATA_REQUEST_TOO_LARGE", "request body is too large")
    auth_error = _verify_auth(request, body, secret)
    if auth_error is not None:
        return auth_error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(422, "TOOL_DATA_JSON_INVALID", str(exc))
    if not isinstance(payload, dict):
        return _error(422, "TOOL_DATA_OBJECT_REQUIRED", "request body must be an object")
    return dict(payload)


def _verify_auth(request: Request, body: bytes, secret: str) -> JSONResponse | None:
    service = request.headers.get(_SERVICE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(401, "TOOL_DATA_CALLER_FORBIDDEN", "internal authentication failed")
    try:
        timestamp = int(request.headers.get(_TIMESTAMP_HEADER, ""))
    except ValueError:
        return _error(401, "TOOL_DATA_TIMESTAMP_INVALID", "internal authentication failed")
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(401, "TOOL_DATA_TIMESTAMP_EXPIRED", "internal authentication failed")
    signature = request.headers.get(_SIGNATURE_HEADER)
    if signature is None or len(signature) != 64:
        return _error(401, "TOOL_DATA_SIGNATURE_INVALID", "internal authentication failed")
    body_hash = hashlib.sha256(body).hexdigest()
    message = (
        f"{service}\n{timestamp}\n{request.method.upper()}\n{request.url.path}\n{body_hash}"
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(401, "TOOL_DATA_SIGNATURE_INVALID", "internal authentication failed")
    return None


def _required_string(payload: dict[str, Any], key: str, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"TOOL_DATA_FIELD_INVALID:{key}")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
