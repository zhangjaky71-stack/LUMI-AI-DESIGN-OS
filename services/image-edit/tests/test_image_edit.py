from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from lumi_artifacts.history import ArtifactHistory
from lumi_artifacts.model import Artifact, ArtifactBranch, ArtifactVersion
from lumi_model_gateway import (
    Capability,
    CostConfidence,
    CostEstimate,
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    ModelRequest,
    ModelRouter,
    NoRouteError,
    ProviderLatencyClass,
    ProviderModel,
)

from lumi_image_edit.artifact_adapter import ArtifactHistoryImageEditAdapter
from lumi_image_edit.inmemory import (
    MemoryComposite,
    MemoryCost,
    MemoryEditedOutput,
    MemoryEvents,
    MemoryStructuralEdit,
    PassingEditValidator,
    ScriptedEditGateway,
    gateway_result,
)
from lumi_image_edit.mask import NormalizedRect, build_mask_spec, normalized_to_pixels
from lumi_image_edit.model import (
    EditFinding,
    EditIntent,
    EditValidationReport,
    ImageEditSpec,
    PixelRect,
    ProtectedRegion,
    SourceImageRef,
)
from lumi_image_edit.pipeline import ImageEditPipeline
from lumi_image_edit.ports import StoredEditedImage
from lumi_image_edit.repository import ImageEditOperationConflict, InMemoryImageEditRepository
from lumi_image_edit.validation import CompositeEditValidator

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
OP = "00000000-0000-0000-0000-000000000004"
ARTIFACT = "00000000-0000-0000-0000-000000000010"
BRANCH = "00000000-0000-0000-0000-000000000011"
SOURCE_VERSION = "00000000-0000-0000-0000-000000000012"


def source(*, commercial: bool = True) -> SourceImageRef:
    return SourceImageRef(
        organization_id=ORG,
        project_id=PROJECT,
        artifact_id=ARTIFACT,
        artifact_version_id=SOURCE_VERSION,
        asset_id="asset-source",
        asset_version="v3",
        durable_ref="asset:source@v3",
        checksum_sha256="a" * 64,
        width=1000,
        height=1000,
        mime_type="image/png",
        rights="USER_OWNED" if commercial else "UNKNOWN",
        commercial_use_allowed=commercial,
    )


def mask(src: SourceImageRef | None = None, *, rect: PixelRect | None = None):
    src = src or source()
    return build_mask_spec(
        source=src,
        mask_id="mask-1",
        version="v1",
        source_kind="USER_BRUSH",
        editable_rect=rect or PixelRect(0, 0, 500, 1000),
        mask_bytes=b"mask-v1",
        durable_ref="mask:mask-1@v1",
    )


def spec(
    *,
    action: str = "REPLACE_BACKGROUND",
    intent_value: object | None = None,
    selected: tuple[str, ...] = (),
    edit_mask=True,
    protected: tuple[ProtectedRegion, ...] = (),
    commercial: bool = True,
    operation_id: str = OP,
    identity: tuple[str, ...] = (),
    allow_broad: bool = False,
) -> ImageEditSpec:
    src = source(commercial=commercial)
    return ImageEditSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=operation_id,
        source=src,
        intent=EditIntent(
            action=action,
            instruction="change only the background to black",
            selected_node_ids=selected,
            value=intent_value,
            allow_broad_change=allow_broad,
        ),
        constraints=(),
        protected_regions=protected,
        mask=mask(src) if edit_mask else None,
        brand_rule_set_version="brand-rules:v4",
        identity_requirement_ids=identity,
        budget_limit_usd=Decimal("1.00"),
        code_git_sha="b" * 40,
        design_document_id="design-doc-1" if selected else None,
        design_document_version=7 if selected else None,
        selected_node_kind="IMAGE" if selected else None,
        seed=42,
    )


def edited(name: str = "edited") -> StoredEditedImage:
    return StoredEditedImage(
        storage_key=f"org/{ORG}/edits/{name}.png",
        checksum_sha256=("c" if name == "edited" else "d") * 64,
        mime_type="image/png",
        size_bytes=2048,
        width=1000,
        height=1000,
        durable_asset_ref=f"asset:{name}@v1",
    )


def history() -> ArtifactHistory:
    h = ArtifactHistory()
    h.add_artifact(Artifact(id=ARTIFACT, organization_id=ORG, project_id=PROJECT, type="RASTER_IMAGE", title="source"))
    h.add_branch(ArtifactBranch(id=BRANCH, organization_id=ORG, artifact_id=ARTIFACT, name="main", base_version_id=None, head_version_id=None, created_by="user"))
    h.add_version(ArtifactVersion(
        id=SOURCE_VERSION,
        organization_id=ORG,
        artifact_id=ARTIFACT,
        branch_id=BRANCH,
        parent_version_id=None,
        schema_version="raster-image-v1",
        version_number=3,
        status="READY",
        content_hash="a" * 64,
        constraint_snapshot_hash="e" * 64,
        created_by_type="USER",
        created_by_id="user",
        created_at=__import__("datetime").datetime.datetime(2026, 8, 14, tzinfo=__import__("datetime").datetime.timezone.utc),
    ))
    return h


def pipeline(*, gateway: ScriptedEditGateway, validator: object | None = None, composite: MemoryComposite | None = None, structural: MemoryStructuralEdit | None = None):
    repo = InMemoryImageEditRepository()
    structural_port = structural or MemoryStructuralEdit()
    output = MemoryEditedOutput({"fixture://edited.png": edited(), "fixture://composited.png": edited("composited")})
    h = history()
    artifact_port = ArtifactHistoryImageEditAdapter(h)
    costs = MemoryCost()
    events = MemoryEvents()
    p = ImageEditPipeline(
        repository=repo,
        structural=structural_port,
        gateway=gateway,
        output=output,
        validator=validator or PassingEditValidator(),  # type: ignore[arg-type]
        composite=composite or MemoryComposite(),
        artifacts=artifact_port,
        costs=costs,
        events=events,
    )
    return p, repo, structural_port, h, artifact_port, costs, events


def test_structural_resize_uses_no_model_and_unknown_rights_do_not_block_local_edit() -> None:
    gateway = ScriptedEditGateway(())
    p, _, structural_port, _, _, costs, _ = pipeline(gateway=gateway)
    job = asyncio.run(p.start(spec(
        action="RESIZE_TEXT",
        intent_value={"width": 600, "height": 120},
        selected=("title",),
        edit_mask=False,
        commercial=False,
    )))
    assert job.status == "COMPLETED"
    assert job.route == "STRUCTURAL_IR_EDIT"
    assert gateway.invoke_count == 0
    assert structural_port.calls[0][0].type == "RESIZE_NODE"
    assert not costs.records


def test_normalized_mask_coordinate_is_explicit_source_pixel_space() -> None:
    rect = normalized_to_pixels(NormalizedRect(0.10, 0.20, 0.50, 0.25), 1000, 800)
    assert rect == PixelRect(100, 160, 500, 200)


def test_mask_version_is_bound_to_source_checksum_and_dimensions() -> None:
    src = source()
    original = mask(src)
    changed = replace(src, checksum_sha256="f" * 64)
    with pytest.raises(ValueError, match="MASK_SOURCE_CHECKSUM_MISMATCH"):
        replace(spec(), source=changed, mask=original)


def test_hard_protected_region_overlap_blocks_before_provider() -> None:
    protected = (ProtectedRegion(
        region_id="product",
        role="PRODUCT",
        rect=PixelRect(250, 0, 300, 1000),
        severity="HARD",
        source_checksum_sha256="a" * 64,
        identity_id="product-1",
    ),)
    gateway = ScriptedEditGateway((gateway_result(),))
    p, *_ = pipeline(gateway=gateway)
    with pytest.raises(ValueError, match="MASK_OVERLAPS_HARD_PROTECTED_REGION"):
        asyncio.run(p.start(spec(protected=protected)))
    assert gateway.invoke_count == 0


class PassingIntended:
    async def validate_intended_change(self, **kwargs: object) -> tuple[EditFinding, ...]:
        return (EditFinding(validator="intended-change", status="PASS", severity="HARD", reason_code="REQUESTED_REGION_CHANGED"),)


def test_qr_lock_fails_closed_when_qr_decoder_unavailable() -> None:
    protected = (ProtectedRegion(
        region_id="qr",
        role="QR",
        rect=PixelRect(700, 700, 200, 200),
        severity="HARD",
        source_checksum_sha256="a" * 64,
        expected_qr_payload="https://example.test/order",
    ),)
    validator = CompositeEditValidator(intended_change=PassingIntended())
    report = asyncio.run(validator.validate(spec=spec(protected=protected), plan=__import__("lumi_image_edit.planner", fromlist=["plan_edit"]).plan_edit(spec(protected=protected)), candidate=edited()))
    assert report.decision == "REJECT"
    assert any(item.reason_code == "IMAGE_EDIT_QR_VALIDATOR_UNAVAILABLE" for item in report.findings)


class SequenceValidator:
    def __init__(self, reports: tuple[EditValidationReport, ...]) -> None:
        self.reports = list(reports)
        self.calls = 0

    async def validate(self, **kwargs: object) -> EditValidationReport:
        del kwargs
        self.calls += 1
        return self.reports.pop(0)


def fail_protected() -> EditValidationReport:
    return EditValidationReport(findings=(EditFinding(
        validator="protected-region",
        status="FAIL",
        severity="HARD",
        reason_code="PROTECTED_REGION_CHANGED",
        score=0.90,
        threshold=0.985,
    ),))


def pass_report() -> EditValidationReport:
    return EditValidationReport(findings=(EditFinding(
        validator="protected-region",
        status="PASS",
        severity="HARD",
        reason_code="PROTECTED_REGION_UNCHANGED",
        score=0.999,
        threshold=0.985,
    ),))


def test_protected_region_failure_uses_composite_fallback_then_revalidates() -> None:
    protected = (ProtectedRegion(
        region_id="logo",
        role="LOGO",
        rect=PixelRect(700, 100, 100, 100),
        severity="HARD",
        source_checksum_sha256="a" * 64,
    ),)
    validator = SequenceValidator((fail_protected(), pass_report()))
    composite = MemoryComposite(replacement=edited("composited"))
    gateway = ScriptedEditGateway((gateway_result(),))
    p, _, _, h, _, _, _ = pipeline(gateway=gateway, validator=validator, composite=composite)
    job = asyncio.run(p.start(spec(protected=protected)))
    assert composite.calls == 1
    assert validator.calls == 2
    assert job.status == "COMPLETED"
    assert h.branches[BRANCH].head_version_id == job.result_artifact_version_id


def test_pass_creates_append_only_version_lineage_and_never_mutates_source() -> None:
    gateway = ScriptedEditGateway((gateway_result(),))
    p, _, _, h, artifact_port, _, _ = pipeline(gateway=gateway)
    job = asyncio.run(p.start(spec()))
    assert job.status == "COMPLETED"
    assert job.result_artifact_version_id is not None
    version = h.versions[job.result_artifact_version_id]
    assert version.parent_version_id == SOURCE_VERSION
    assert version.version_number == 4
    assert h.versions[SOURCE_VERSION].content_hash == "a" * 64
    assert h.branches[BRANCH].head_version_id == version.id
    assert any(edge.type == "EDITED_FROM" and edge.from_version_id == SOURCE_VERSION and edge.to_version_id == version.id for edge in h.edges.values())
    assert job.provenance_snapshot_id in artifact_port.edit_provenance


def test_soft_repair_candidate_remains_draft_and_does_not_advance_head() -> None:
    report = EditValidationReport(findings=(EditFinding(validator="intended-change", status="FAIL", severity="SOFT", reason_code="WEAK_CHANGE"),))
    gateway = ScriptedEditGateway((gateway_result(),))
    p, _, _, h, _, _, _ = pipeline(gateway=gateway, validator=SequenceValidator((report,)))
    job = asyncio.run(p.start(spec()))
    assert job.status == "REPAIR_REQUIRED"
    assert h.versions[job.result_artifact_version_id].status == "DRAFT"  # type: ignore[index]
    assert h.branches[BRANCH].head_version_id == SOURCE_VERSION


def test_hard_rejected_candidate_is_auditable_but_does_not_advance_head() -> None:
    gateway = ScriptedEditGateway((gateway_result(),))
    p, _, _, h, _, _, _ = pipeline(gateway=gateway, validator=SequenceValidator((fail_protected(),)))
    job = asyncio.run(p.start(spec()))
    assert job.status == "REJECTED"
    assert h.versions[job.result_artifact_version_id].status == "REJECTED"  # type: ignore[index]
    assert h.branches[BRANCH].head_version_id == SOURCE_VERSION


def test_pixel_pass_updates_canvas_via_replace_asset_after_artifact_ready() -> None:
    gateway = ScriptedEditGateway((gateway_result(),))
    structural_port = MemoryStructuralEdit()
    p, _, _, _, _, _, _ = pipeline(gateway=gateway, structural=structural_port)
    job = asyncio.run(p.start(spec(selected=("image-node",))))
    assert job.status == "COMPLETED"
    assert job.result_design_document_version_id is not None
    assert structural_port.calls[-1][0].type == "REPLACE_ASSET"
    assert structural_port.calls[-1][0].payload["asset_ref"] == "asset:edited@v1"


def test_duplicate_operation_reuses_job_without_second_paid_call() -> None:
    gateway = ScriptedEditGateway((gateway_result(),))
    p, *_ = pipeline(gateway=gateway)
    first = asyncio.run(p.start(spec()))
    second = asyncio.run(p.start(spec()))
    assert second == first
    assert gateway.invoke_count == 1


def test_same_operation_with_changed_semantics_fails_closed() -> None:
    gateway = ScriptedEditGateway((gateway_result(),))
    p, *_ = pipeline(gateway=gateway)
    asyncio.run(p.start(spec()))
    changed = spec()
    changed = replace(changed, intent=replace(changed.intent, instruction="remove the cup"))
    with pytest.raises(ImageEditOperationConflict):
        asyncio.run(p.start(changed))


def test_pending_edit_resumes_without_new_invoke() -> None:
    pending = gateway_result(status="PENDING", output_ref=None)
    gateway = ScriptedEditGateway((pending, gateway_result()))
    p, *_ = pipeline(gateway=gateway)
    first = asyncio.run(p.start(spec()))
    assert first.status == "PROVIDER_PENDING"
    resumed = asyncio.run(p.resume_pending(organization_id=ORG, operation_id=OP))
    assert resumed.status == "COMPLETED"
    assert gateway.invoke_count == 1
    assert gateway.poll_count == 1


class MaskOnlyProvider:
    def __init__(self, capabilities: frozenset[Capability]) -> None:
        self._descriptor = ProviderModel(
            provider="mask-only",
            model="m1",
            capabilities=capabilities,
            quality_score=95,
            latency_class=ProviderLatencyClass.FAST,
        )

    @property
    def descriptor(self) -> ProviderModel:
        return self._descriptor

    def validate(self, request: ModelRequest) -> None:
        del request

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        del request
        return CostEstimate(amount_usd=Decimal("0.01"), confidence=CostConfidence.EXACT)



def model_request() -> ModelRequest:
    return ModelRequest(
        organization_id=UUID(ORG),
        project_id=UUID(PROJECT),
        task_id=UUID(TASK),
        operation_id=UUID(OP),
        capability=Capability.IMAGE_MASK_EDIT,
        inputs={"instruction":"background black"},
        constraints={"required_capabilities":[Capability.IMAGE_REFERENCE_CONSISTENCY.value]},
    )


def test_router_rejects_mask_provider_without_required_reference_consistency() -> None:
    provider = MaskOnlyProvider(frozenset({Capability.IMAGE_MASK_EDIT}))
    registry = InMemoryProviderRegistry((provider,))  # type: ignore[arg-type]
    router = ModelRouter(registry=registry, health=InMemoryProviderHealthRegistry())
    with pytest.raises(NoRouteError, match="ADDITIONAL_CAPABILITY_MISMATCH"):
        asyncio.run(router.route(model_request()))


def test_router_accepts_provider_with_mask_and_reference_consistency() -> None:
    provider = MaskOnlyProvider(frozenset({Capability.IMAGE_MASK_EDIT, Capability.IMAGE_REFERENCE_CONSISTENCY}))
    registry = InMemoryProviderRegistry((provider,))  # type: ignore[arg-type]
    router = ModelRouter(registry=registry, health=InMemoryProviderHealthRegistry())
    decision = asyncio.run(router.route(model_request()))
    assert decision.candidates[0].reason_codes[-1] == "ADDITIONAL_CAPABILITIES_MATCH"
