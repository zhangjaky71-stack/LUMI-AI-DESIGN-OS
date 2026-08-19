from __future__ import annotations

import asyncio
from typing import Any

from .audit import NullAuditSink, ToolAuditRecord, redact_arguments
from .contracts import (
    ApprovalDecision,
    ToolAdapterOutput,
    ToolApproval,
    ToolCallStatus,
    ToolDefinition,
    ToolIdempotency,
    ToolRequest,
    ToolResult,
    ToolSideEffectContext,
    ToolSideEffectResponse,
    canonical_json_bytes,
)
from .errors import (
    ToolAdapterExecutionError,
    ToolApprovalDeniedError,
    ToolAuditUnavailableError,
    ToolGatewayError,
    ToolIdempotencyRequiredError,
    ToolInternalError,
    ToolOutputOffloadRequiredError,
    ToolSideEffectGuardRequiredError,
    ToolTimeoutError,
)
from .policy import ToolApprovalPolicy, ToolPermissionPolicy
from .ports import ApprovalResolver, AuditSink, ResultOffloader, SideEffectGuard, ToolAdapter
from .registry import ToolRegistry
from .schema import SchemaValidator


class ToolGateway:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        adapters: dict[str, ToolAdapter],
        permission_policy: ToolPermissionPolicy | None = None,
        approval_policy: ToolApprovalPolicy | None = None,
        approval_resolver: ApprovalResolver | None = None,
        side_effect_guard: SideEffectGuard | None = None,
        result_offloader: ResultOffloader | None = None,
        audit_sink: AuditSink | None = None,
        schema_validator: SchemaValidator | None = None,
    ) -> None:
        self.registry = registry
        self.adapters = dict(adapters)
        self.permission_policy = permission_policy or ToolPermissionPolicy()
        self.approval_policy = approval_policy or ToolApprovalPolicy()
        self.approval_resolver = approval_resolver
        self.side_effect_guard = side_effect_guard
        self.result_offloader = result_offloader
        self.audit_sink = audit_sink or NullAuditSink()
        self.schema_validator = schema_validator or SchemaValidator()

    async def invoke(self, request: ToolRequest) -> ToolResult:
        definition = self.registry.resolve(request.name, request.version)
        resolved_tool = definition.key
        approval_id: str | None = None
        try:
            self.permission_policy.require(definition, request.permission_context)
            self.schema_validator.validate_input(definition.input_schema, request.arguments)

            approval = await self._approval(definition, request)
            approval_id = approval.approval_id
            if approval.decision == ApprovalDecision.REQUIRED:
                result = ToolResult(
                    tool_call_id=request.tool_call_id,
                    status=ToolCallStatus.APPROVAL_REQUIRED,
                    resolved_name=definition.name,
                    resolved_version=definition.version,
                    summary=approval.reason_code or "approval required",
                    approval_id=approval.approval_id,
                    error_code="TOOL_APPROVAL_REQUIRED",
                )
                await self._audit(request, definition, result)
                return result
            if approval.decision == ApprovalDecision.DENIED:
                result = ToolResult(
                    tool_call_id=request.tool_call_id,
                    status=ToolCallStatus.DENIED,
                    resolved_name=definition.name,
                    resolved_version=definition.version,
                    summary=approval.reason_code or "approval denied",
                    approval_id=approval.approval_id,
                    error_code=ToolApprovalDeniedError.code,
                )
                await self._audit(request, definition, result)
                return result

            adapter = self.adapters.get(definition.key)
            if adapter is None:
                raise ToolGatewayError(f"TOOL_ADAPTER_NOT_REGISTERED:{resolved_tool}")

            response = await self._execute(definition, request, adapter)
            self.schema_validator.validate_output(definition.output_schema, response.output.data)
            result = await self._normalize_result(
                definition=definition,
                request=request,
                response=response,
                approval_id=approval_id,
            )
            await self._audit(
                request,
                definition,
                result,
                side_effect_operation_id=response.operation_id,
            )
            return result
        except ToolAuditUnavailableError:
            # Never recursively emit another audit event for an audit-delivery failure.
            # For side effects, NODE-20 already owns replay safety if the caller retries.
            raise
        except ToolGatewayError as exc:
            await self._audit_error(
                request,
                resolved_tool=resolved_tool,
                risk=definition.risk.value,
                sensitive_fields=definition.sensitive_fields,
                error_code=exc.code,
                approval_id=approval_id,
            )
            raise
        except Exception as exc:
            try:
                await self._audit_error(
                    request,
                    resolved_tool=resolved_tool,
                    risk=definition.risk.value,
                    sensitive_fields=definition.sensitive_fields,
                    error_code=ToolInternalError.code,
                    approval_id=approval_id,
                )
            except ToolAuditUnavailableError as audit_exc:
                raise audit_exc from exc
            raise ToolInternalError("unexpected Tool Gateway execution failure") from exc

    async def _approval(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolApproval:
        baseline = self.approval_policy.decision(definition)
        if baseline.decision != ApprovalDecision.REQUIRED:
            return baseline
        if self.approval_resolver is None:
            return baseline
        resolved = await self.approval_resolver.resolve(definition, request)
        if resolved.decision == ApprovalDecision.APPROVED:
            return resolved
        if resolved.decision == ApprovalDecision.DENIED:
            return resolved
        return ToolApproval(
            ApprovalDecision.REQUIRED,
            approval_id=resolved.approval_id,
            reason_code=resolved.reason_code or baseline.reason_code,
        )

    async def _execute(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
        adapter: ToolAdapter,
    ) -> ToolSideEffectResponse:
        async def call_adapter() -> ToolAdapterOutput:
            try:
                return await asyncio.wait_for(
                    adapter.invoke(definition, request),
                    timeout=definition.timeout_seconds,
                )
            except ToolGatewayError:
                raise
            except TimeoutError as exc:
                raise ToolTimeoutError(
                    f"tool exceeded {definition.timeout_seconds:g}s timeout"
                ) from exc
            except Exception as exc:
                raise ToolAdapterExecutionError(
                    f"adapter failed for {definition.key}"
                ) from exc

        if definition.idempotency == ToolIdempotency.NOT_REQUIRED:
            return ToolSideEffectResponse(await call_adapter(), replayed=False)
        if not request.idempotency_key:
            raise ToolIdempotencyRequiredError(
                f"idempotency key required for {definition.key}"
            )
        if self.side_effect_guard is None:
            raise ToolSideEffectGuardRequiredError(
                f"side-effect guard required for {definition.key}"
            )
        context = ToolSideEffectContext(
            organization_id=request.organization_id,
            operation_type=f"tool:{definition.name}:{definition.version}",
            idempotency_key=request.idempotency_key,
            request={
                "tool": definition.key,
                "agent_run_id": str(request.agent_run_id),
                "task_id": str(request.task_id),
                "arguments": request.arguments,
                "purpose": request.purpose,
            },
            business_scope_id=request.task_id,
        )
        return await self.side_effect_guard.execute(context, call_adapter)

    async def _normalize_result(
        self,
        *,
        definition: ToolDefinition,
        request: ToolRequest,
        response: ToolSideEffectResponse,
        approval_id: str | None,
    ) -> ToolResult:
        output = response.output
        payload = canonical_json_bytes(output.data)
        if len(payload) <= definition.max_inline_output_bytes:
            return ToolResult(
                tool_call_id=request.tool_call_id,
                status=ToolCallStatus.SUCCEEDED,
                resolved_name=definition.name,
                resolved_version=definition.version,
                summary=output.summary,
                data=output.data,
                resource_refs=output.resource_refs,
                replayed=response.replayed,
                approval_id=approval_id,
            )
        if self.result_offloader is None:
            raise ToolOutputOffloadRequiredError(
                f"tool output is {len(payload)} bytes; offloader required"
            )
        ref = await self.result_offloader.store(
            organization_id=str(request.organization_id),
            tool_call_id=str(request.tool_call_id),
            resolved_tool=definition.key,
            payload=payload,
        )
        return ToolResult(
            tool_call_id=request.tool_call_id,
            status=ToolCallStatus.SUCCEEDED,
            resolved_name=definition.name,
            resolved_version=definition.version,
            summary=output.summary or "Full tool result stored outside Agent context.",
            data=_inline_preview(output.data),
            resource_refs=output.resource_refs,
            truncated=True,
            full_result_ref=ref,
            replayed=response.replayed,
            approval_id=approval_id,
        )

    async def _audit(
        self,
        request: ToolRequest,
        definition: ToolDefinition,
        result: ToolResult,
        *,
        side_effect_operation_id: str | None = None,
    ) -> None:
        await self._record_audit(
            ToolAuditRecord(
                tool_call_id=str(request.tool_call_id),
                organization_id=str(request.organization_id),
                actor_id=request.permission_context.actor_id,
                actor_agent=request.actor_agent,
                resolved_tool=definition.key,
                risk=definition.risk.value,
                purpose=request.purpose,
                status=result.status.value,
                trace_id=request.trace_id,
                arguments=redact_arguments(
                    request.arguments,
                    sensitive_fields=definition.sensitive_fields,
                ),
                replayed=result.replayed,
                side_effect_operation_id=side_effect_operation_id,
                approval_id=result.approval_id,
                error_code=result.error_code,
            )
        )

    async def _audit_error(
        self,
        request: ToolRequest,
        *,
        resolved_tool: str,
        risk: str,
        sensitive_fields: frozenset[str],
        error_code: str,
        approval_id: str | None,
    ) -> None:
        await self._record_audit(
            ToolAuditRecord(
                tool_call_id=str(request.tool_call_id),
                organization_id=str(request.organization_id),
                actor_id=request.permission_context.actor_id,
                actor_agent=request.actor_agent,
                resolved_tool=resolved_tool,
                risk=risk,
                purpose=request.purpose,
                status=ToolCallStatus.FAILED.value,
                trace_id=request.trace_id,
                arguments=redact_arguments(
                    request.arguments,
                    sensitive_fields=sensitive_fields,
                ),
                approval_id=approval_id,
                error_code=error_code,
            )
        )

    async def _record_audit(self, event: ToolAuditRecord) -> None:
        try:
            await self.audit_sink.record(event)
        except ToolAuditUnavailableError:
            raise
        except Exception as exc:
            raise ToolAuditUnavailableError(
                "durable Tool Gateway audit delivery failed"
            ) from exc


def _inline_preview(value: Any, *, depth: int = 0) -> Any:
    if depth >= 2:
        if isinstance(value, dict):
            return {"_truncated": True, "keys": list(value)[:10]}
        if isinstance(value, list):
            return {"_truncated": True, "items": len(value)}
        if isinstance(value, str) and len(value) > 512:
            return value[:512] + "…"
        return value
    if isinstance(value, dict):
        return {
            key: _inline_preview(child, depth=depth + 1)
            for key, child in list(value.items())[:20]
        }
    if isinstance(value, list):
        return [_inline_preview(child, depth=depth + 1) for child in value[:20]]
    if isinstance(value, str) and len(value) > 1024:
        return value[:1024] + "…"
    return value
