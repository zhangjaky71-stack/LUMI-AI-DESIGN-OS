from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.api.v1.context import RequestContext
from lumi_api.api.v1.contracts import GenerationCreate, GenerationResource
from lumi_api.api.v1.errors import ApiProblem
from lumi_api.api.v1.services import ApiV1Gateway
from lumi_api.persistence.models import Generation

from .errors import GenerationConflict, GenerationControlPlaneError, GenerationInvalid, GenerationNotFound
from .service import ImageGenerationControlPlane


class GenerationRuntimeGateway:
    """Decorator that adds hosted generation operations to an existing V1 gateway."""

    def __init__(
        self,
        base: ApiV1Gateway,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._base = base
        self._session_factory = session_factory

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    async def create_generation(
        self,
        context: RequestContext,
        payload: GenerationCreate,
        idempotency_key: str,
    ) -> GenerationResource:
        self._require(context, "project.write")
        async with self._session_factory() as session, session.begin():
            try:
                row = await ImageGenerationControlPlane(session).create(
                    organization_id=context.organization_id,
                    payload=payload,
                    idempotency_key=idempotency_key,
                    trace_id=context.trace_id,
                )
            except GenerationControlPlaneError as exc:
                raise self._problem(exc) from exc
            await session.refresh(row)
            return self._resource(row)

    async def get_generation(
        self,
        context: RequestContext,
        generation_id: UUID,
    ) -> GenerationResource:
        self._require(context, "project.read")
        async with self._session_factory() as session, session.begin():
            try:
                row = await ImageGenerationControlPlane(session).get(
                    organization_id=context.organization_id,
                    generation_id=generation_id,
                )
            except GenerationControlPlaneError as exc:
                raise self._problem(exc) from exc
            return self._resource(row)

    @staticmethod
    def _resource(row: Generation) -> GenerationResource:
        return GenerationResource(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            task_id=row.task_id,
            agent_run_id=row.agent_run_id,
            operation_id=row.operation_id,
            capability=row.capability,
            provider=row.provider,
            model=row.model,
            status=row.status,
            request=dict(row.request_json),
            result=dict(row.result_json),
            created_at=row.created_at,
        )

    @staticmethod
    def _require(context: RequestContext, permission: str) -> UUID:
        if context.actor_id is None or permission not in context.permissions:
            raise ApiProblem(status=403, code="PERMISSION_DENIED", title="Permission denied")
        return context.actor_id

    @staticmethod
    def _problem(error: GenerationControlPlaneError) -> ApiProblem:
        if isinstance(error, GenerationNotFound):
            return ApiProblem(
                status=404,
                code=error.code,
                title="Resource not found",
                detail=str(error),
            )
        if isinstance(error, GenerationConflict):
            return ApiProblem(
                status=409,
                code=error.code,
                title="Generation conflict",
                detail=str(error),
            )
        if isinstance(error, GenerationInvalid):
            return ApiProblem(
                status=422,
                code=error.code,
                title="Invalid generation request",
                detail=str(error),
            )
        return ApiProblem(
            status=500,
            code="GENERATION_OPERATION_FAILED",
            title="Generation operation failed",
        )
