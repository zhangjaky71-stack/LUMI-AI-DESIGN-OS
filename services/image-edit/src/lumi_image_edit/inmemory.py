from __future__ import annotations

from decimal import Decimal

from .model import (
    EditFinding,
    EditPlan,
    EditValidationReport,
    GatewayEditResult,
    ImageEditSpec,
    MaskSpec,
    SourceImageRef,
    StructuralEditOperation,
)
from .ports import StoredEditedImage, StructuralEditResult


class MemoryStructuralEdit:
    def __init__(self) -> None:
        self.calls: list[tuple[StructuralEditOperation, ...]] = []

    async def apply(self, *, spec: ImageEditSpec, operations: tuple[StructuralEditOperation, ...]) -> StructuralEditResult:
        self.calls.append(operations)
        version = (spec.design_document_version or 0) + 1
        return StructuralEditResult(
            design_document_version_id=f"design-version:{spec.design_document_id}:{version}",
            artifact_version_id=None,
            applied_operation_ids=tuple(item.operation_id for item in operations),
        )


class ScriptedEditGateway:
    def __init__(self, results: tuple[GatewayEditResult, ...]) -> None:
        self.results = list(results)
        self.invoke_count = 0
        self.poll_count = 0

    async def invoke(self, *, spec: ImageEditSpec, plan: EditPlan, mask: MaskSpec | None) -> GatewayEditResult:
        del spec, plan, mask
        self.invoke_count += 1
        if not self.results:
            raise RuntimeError("SCRIPTED_EDIT_GATEWAY_EXHAUSTED")
        return self.results.pop(0)

    async def poll(self, *, spec: ImageEditSpec, plan: EditPlan, pending: GatewayEditResult, mask: MaskSpec | None) -> GatewayEditResult:
        del spec, plan, pending, mask
        self.poll_count += 1
        if not self.results:
            raise RuntimeError("SCRIPTED_EDIT_GATEWAY_EXHAUSTED")
        return self.results.pop(0)


class MemoryEditedOutput:
    def __init__(self, outputs: dict[str, StoredEditedImage]) -> None:
        self.outputs = outputs

    async def materialize_and_store(self, *, spec: ImageEditSpec, output_ref: str, declared_mime_type: str | None) -> StoredEditedImage:
        del spec, declared_mime_type
        try:
            return self.outputs[output_ref]
        except KeyError as exc:
            raise ValueError("IMAGE_EDIT_OUTPUT_INVALID_OR_MISSING") from exc


class MemoryComposite:
    def __init__(self, replacement: StoredEditedImage | None = None) -> None:
        self.replacement = replacement
        self.calls = 0

    async def composite_source_regions(self, *, source: SourceImageRef, candidate: StoredEditedImage, spec: ImageEditSpec) -> StoredEditedImage:
        del source, spec
        self.calls += 1
        return self.replacement or candidate


class PassingEditValidator:
    async def validate(self, *, spec: ImageEditSpec, plan: EditPlan, candidate: StoredEditedImage) -> EditValidationReport:
        del spec, plan, candidate
        return EditValidationReport(findings=(EditFinding(
            validator="fixture",
            status="PASS",
            severity="HARD",
            reason_code="FIXTURE_PASS",
        ),))


class MemoryCost:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(dict(kwargs))


class MemoryEvents:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def emit(self, event_type: str, *, organization_id: str, edit_id: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, {"organization_id": organization_id, "edit_id": edit_id, **payload}))


def gateway_result(
    *,
    status: str = "SUCCEEDED",
    output_ref: str | None = "fixture://edited.png",
    provider: str = "fixture",
    model: str = "edit-v1",
    blocked: bool = False,
) -> GatewayEditResult:
    return GatewayEditResult(
        status=status,  # type: ignore[arg-type]
        provider=provider,
        model=model,
        provider_request_id="provider-edit-1",
        output_ref=output_ref,
        output_mime_type="image/png" if output_ref else None,
        cost_usd=Decimal("0.02"),
        cost_confidence="exact",
        pricing_snapshot_id="price-v1",
        routing_reason_codes=("CAPABILITY_MATCH",),
        safety_metadata={"blocked": blocked},
        seed=42,
    )
