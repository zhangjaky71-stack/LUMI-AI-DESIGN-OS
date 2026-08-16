from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel

from lumi_api.api.v1.ports import ApiV1Service
from lumi_api.api.v1.schemas import (
    AgentRunCreateRequest,
    AgentRunResponse,
    CancelResponse,
    GenerationCreateRequest,
    GenerationResponse,
    ProjectCreateRequest,
    ProjectResponse,
    TaskCreateRequest,
    TaskResponse,
)
from lumi_api.domain.ids import new_uuid7

from .gateway import SideEffectGateway
from .hashing import canonical_request_hash
from .models import CompensationMode, OperationRequest, SideEffectKind, SideEffectOutcome

T = TypeVar("T", bound=BaseModel)


class IdempotentApiService:
    """Decorator for the mutation methods that already require Idempotency-Key.

    Read-only and optimistic-concurrency methods delegate through ``__getattr__``.
    Paid provider execution is intentionally a separate internal operation; an HTTP
    generation-create command must not collapse provider execution into the request lease.
    """

    def __init__(self, inner: ApiV1Service, gateway: SideEffectGateway) -> None:
        self.inner = inner
        self.gateway = gateway

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def _execute_model(
        self,
        *,
        organization_id: UUID,
        operation_type: str,
        idempotency_key: str,
        business_scope_id: str,
        semantic_request: dict[str, Any],
        response_type: type[T],
        response_status: int,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        request = OperationRequest(
            organization_id=organization_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
            request_hash=canonical_request_hash(semantic_request),
            business_scope_id=business_scope_id,
            side_effect_kind=SideEffectKind.GENERIC_WRITE,
            compensation_mode=CompensationMode.COMPENSATABLE,
            paid=False,
        )

        async def effect(_context) -> SideEffectOutcome:
            response = await call()
            return SideEffectOutcome(
                result=response.model_dump(mode="json"),
                response_status=response_status,
            )

        outcome = await self.gateway.execute(
            request,
            effect,
            lease_owner=f"api:{new_uuid7()}",
        )
        return response_type.model_validate(outcome.result)

    async def create_project(
        self,
        organization_id: UUID,
        request: ProjectCreateRequest,
        *,
        idempotency_key: str,
    ) -> ProjectResponse:
        return await self._execute_model(
            organization_id=organization_id,
            operation_type="api.project.create",
            idempotency_key=idempotency_key,
            business_scope_id=str(request.workspace_id),
            semantic_request=request.model_dump(mode="python"),
            response_type=ProjectResponse,
            response_status=201,
            call=lambda: self.inner.create_project(
                organization_id, request, idempotency_key=idempotency_key
            ),
        )

    async def create_task(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: TaskCreateRequest,
        *,
        idempotency_key: str,
    ) -> TaskResponse:
        return await self._execute_model(
            organization_id=organization_id,
            operation_type="api.task.create",
            idempotency_key=idempotency_key,
            business_scope_id=str(project_id),
            semantic_request={"project_id": project_id, "body": request},
            response_type=TaskResponse,
            response_status=201,
            call=lambda: self.inner.create_task(
                organization_id,
                project_id,
                request,
                idempotency_key=idempotency_key,
            ),
        )

    async def create_agent_run(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: AgentRunCreateRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunResponse:
        return await self._execute_model(
            organization_id=organization_id,
            operation_type="api.agent_run.create",
            idempotency_key=idempotency_key,
            business_scope_id=str(project_id),
            semantic_request={"project_id": project_id, "body": request},
            response_type=AgentRunResponse,
            response_status=202,
            call=lambda: self.inner.create_agent_run(
                organization_id,
                project_id,
                request,
                idempotency_key=idempotency_key,
            ),
        )

    async def cancel_agent_run(
        self,
        organization_id: UUID,
        agent_run_id: UUID,
        *,
        idempotency_key: str,
    ) -> CancelResponse:
        return await self._execute_model(
            organization_id=organization_id,
            operation_type="api.agent_run.cancel",
            idempotency_key=idempotency_key,
            business_scope_id=str(agent_run_id),
            semantic_request={"agent_run_id": agent_run_id, "action": "cancel"},
            response_type=CancelResponse,
            response_status=202,
            call=lambda: self.inner.cancel_agent_run(
                organization_id,
                agent_run_id,
                idempotency_key=idempotency_key,
            ),
        )

    async def create_generation(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: GenerationCreateRequest,
        *,
        idempotency_key: str,
    ) -> GenerationResponse:
        return await self._execute_model(
            organization_id=organization_id,
            operation_type="api.generation.create",
            idempotency_key=idempotency_key,
            business_scope_id=str(project_id),
            semantic_request={"project_id": project_id, "body": request},
            response_type=GenerationResponse,
            response_status=202,
            call=lambda: self.inner.create_generation(
                organization_id,
                project_id,
                request,
                idempotency_key=idempotency_key,
            ),
        )
