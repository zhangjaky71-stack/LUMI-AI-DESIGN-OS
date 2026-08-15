from __future__ import annotations

from dataclasses import asdict
from typing import Awaitable, Callable, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from lumi_project_core.approval import (
    ApprovalActor,
    ApprovalEngine,
    ApprovalError,
    ApprovalFeedback,
    ApprovalPolicy,
    ApprovalRecord,
    ApprovalSubject,
)

ApprovalActorResolver = Callable[[Request, str], Awaitable[ApprovalActor]]
ApprovalTypeInput = Literal[
    "CREATIVE_DIRECTION",
    "ARTIFACT_VERSION",
    "BRAND_RULE_SET",
    "BUDGET_INCREASE",
    "EXTERNAL_PUBLISH",
    "DESTRUCTIVE_ACTION",
    "CUSTOM_REVIEW",
]
ApprovalPolicyModeInput = Literal["ANY_ONE", "ALL", "MIN_N", "ROLE_BASED_SEQUENCE"]
ApprovalDecisionInput = Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]


class ApprovalPolicyBody(BaseModel):
    mode: ApprovalPolicyModeInput = "ANY_ONE"
    version: int = 1
    required_permission: str = "artifact.approve"
    required_roles: list[str] = Field(default_factory=list)
    min_approvals: int = 1
    sequence_roles: list[str] = Field(default_factory=list)


class ApprovalRequestBody(BaseModel):
    approval_type: ApprovalTypeInput
    subject_type: str
    subject_id: str
    subject_version: str
    payload_summary: str
    policy: ApprovalPolicyBody = Field(default_factory=ApprovalPolicyBody)
    agent_run_id: str | None = None
    task_id: str | None = None
    expires_at: str | None = None


class ApprovalFeedbackBody(BaseModel):
    comment: str = ""
    node_refs: list[str] = Field(default_factory=list)
    region_refs: list[str] = Field(default_factory=list)
    requested_changes: list[str] = Field(default_factory=list)


class ApprovalDecisionBody(BaseModel):
    decision: ApprovalDecisionInput
    reason: str | None = None
    feedback: ApprovalFeedbackBody | None = None


class ApprovalCancelBody(BaseModel):
    reason: str | None = None


def _approval_json(record: ApprovalRecord) -> dict[str, object]:
    return asdict(record)


def _problem(error: ApprovalError, request_id: str | None) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={
            "code": error.code,
            "message": "Approval request could not be completed.",
            "request_id": request_id,
        },
    )


def create_approval_router(
    *,
    engine: ApprovalEngine,
    resolve_actor: ApprovalActorResolver,
) -> APIRouter:
    router = APIRouter(prefix="/projects/{project_id}/approvals", tags=["approvals"])

    @router.get("")
    async def list_approvals(request: Request, project_id: str):
        actor = await resolve_actor(request, project_id)
        if "project.read" not in actor.permissions:
            raise _problem(ApprovalError("APPROVAL_FORBIDDEN", 403), _request_id(request))
        try:
            items = engine.list_project(actor, project_id)
            return {
                "items": [_approval_json(item) for item in items],
                "current_actor_id": actor.actor_id,
                "can_decide": any(
                    item.status == "PENDING"
                    and item.policy.required_permission in actor.permissions
                    and (
                        not item.policy.required_roles
                        or bool(set(actor.roles).intersection(item.policy.required_roles))
                    )
                    for item in items
                ),
            }
        except ApprovalError as error:
            raise _problem(error, _request_id(request)) from error

    @router.get("/{approval_id}")
    async def get_approval(request: Request, project_id: str, approval_id: str):
        actor = await resolve_actor(request, project_id)
        if "project.read" not in actor.permissions:
            raise _problem(ApprovalError("APPROVAL_FORBIDDEN", 403), _request_id(request))
        try:
            return _approval_json(engine.get(actor, project_id, approval_id))
        except ApprovalError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("")
    async def request_approval(request: Request, project_id: str, body: ApprovalRequestBody):
        actor = await resolve_actor(request, project_id)
        if "project.write" not in actor.permissions:
            raise _problem(ApprovalError("APPROVAL_FORBIDDEN", 403), _request_id(request))
        try:
            policy = ApprovalPolicy(
                mode=body.policy.mode,
                version=body.policy.version,
                required_permission=body.policy.required_permission,
                required_roles=tuple(body.policy.required_roles),
                min_approvals=body.policy.min_approvals,
                sequence_roles=tuple(body.policy.sequence_roles),
            )
            approval = engine.request(
                actor,
                project_id=project_id,
                approval_type=body.approval_type,
                subject=ApprovalSubject(body.subject_type, body.subject_id, body.subject_version),
                policy=policy,
                payload_summary=body.payload_summary,
                agent_run_id=body.agent_run_id,
                task_id=body.task_id,
                expires_at=body.expires_at,
            )
            return _approval_json(approval)
        except ApprovalError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/{approval_id}:decide")
    async def decide_approval(
        request: Request,
        project_id: str,
        approval_id: str,
        body: ApprovalDecisionBody,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        actor = await resolve_actor(request, project_id)
        try:
            feedback = None
            if body.feedback is not None:
                feedback = ApprovalFeedback(
                    comment=body.feedback.comment,
                    node_refs=tuple(body.feedback.node_refs),
                    region_refs=tuple(body.feedback.region_refs),
                    requested_changes=tuple(body.feedback.requested_changes),
                )
            return _approval_json(
                engine.decide(
                    actor,
                    project_id=project_id,
                    approval_id=approval_id,
                    decision=body.decision,
                    idempotency_key=idempotency_key,
                    reason=body.reason,
                    feedback=feedback,
                )
            )
        except ApprovalError as error:
            raise _problem(error, _request_id(request)) from error

    @router.post("/{approval_id}:cancel")
    async def cancel_approval(
        request: Request, project_id: str, approval_id: str, body: ApprovalCancelBody
    ):
        actor = await resolve_actor(request, project_id)
        try:
            return _approval_json(
                engine.cancel(actor, project_id=project_id, approval_id=approval_id, reason=body.reason)
            )
        except ApprovalError as error:
            raise _problem(error, _request_id(request)) from error

    return router


def _request_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    return value[:128] if value else None
