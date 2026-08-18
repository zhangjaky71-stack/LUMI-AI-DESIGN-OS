from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lumi_api.auto_repair.design_ir_backend import Node38StructuralRepairBackend
from lumi_api.auto_repair.executor_adapter import CompositeRepairExecutor
from lumi_auto_repair import (
    AutoRepairJob,
    AutoRepairTaskSpec,
    BudgetReservation,
    RepairCandidate,
    RepairDirective,
    RepairKind,
    RepairLoopStatus,
    RepairPlan,
    RepairPolicySnapshot,
    RepairQualitySnapshot,
    RepairSourceSnapshot,
)
from lumi_api.design_ir.primitives import Transform2D
from lumi_image_edit import EditIntent, ImageEditSpec, SourceImageRef


def _image_spec(*, target_branch_id: str | None) -> ImageEditSpec:
    organization_id = str(uuid4())
    project_id = str(uuid4())
    return ImageEditSpec(
        organization_id=organization_id,
        project_id=project_id,
        task_id=str(uuid4()),
        operation_id=str(uuid4()),
        source=SourceImageRef(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=str(uuid4()),
            artifact_version_id=str(uuid4()),
            asset_id=str(uuid4()),
            asset_version="1",
            durable_ref="private-bucket/source.png",
            checksum_sha256="a" * 64,
            width=1024,
            height=1024,
            mime_type="image/png",
            rights_assertion="owner-upload",
            commercial_use_allowed=True,
        ),
        intent=EditIntent(action="REMOVE", instruction="remove noise"),
        constraints=(),
        protected_regions=(),
        mask=None,
        brand_rule_set_version=None,
        identity_requirement_ids=(),
        budget_limit_usd=Decimal("1.00"),
        code_git_sha="b" * 40,
        target_branch_id=target_branch_id,
    )


def test_image_edit_target_branch_is_part_of_semantic_identity() -> None:
    branch = str(uuid4())
    isolated = _image_spec(target_branch_id=branch)
    normal = replace(isolated, target_branch_id=None)
    assert isolated.semantic_hash != normal.semantic_hash


def test_image_edit_rejects_empty_target_branch() -> None:
    with pytest.raises(ValueError, match="IMAGE_EDIT_TARGET_BRANCH_INVALID"):
        _image_spec(target_branch_id=" ")


def test_structural_set_property_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="REPAIR_SET_PROPERTY_NOT_ALLOWLISTED"):
        Node38StructuralRepairBackend._compile_property(
            uuid4(),
            SimpleNamespace(transform=Transform2D()),
            {"property": "raw_json", "value": {"unsafe": True}},
        )


class _Structural:
    async def execute_design_ops(self, *, job, plan, repair_branch_id):
        raise AssertionError("structural backend should not run")


class _Local:
    def __init__(self) -> None:
        self.calls = 0

    async def estimate_local_edit(self, *, job, plan):
        raise AssertionError("estimate not needed")

    async def execute_local_edit(self, *, job, plan, repair_branch_id):
        self.calls += 1
        return RepairCandidate(
            artifact_version_id=str(uuid4()),
            artifact_content_hash="d" * 64,
            repair_branch_id=repair_branch_id,
            actual_cost_usd=Decimal("0.10"),
            provider="provider-a",
            model="model-a",
            provider_request_id="request-a",
        )


class _Generation:
    async def estimate_regeneration(self, *, job, plan):
        raise AssertionError("generation backend should not run")

    async def execute_regeneration(self, *, job, plan, repair_branch_id, reservation):
        raise AssertionError("generation backend should not run")


def _repair_job() -> AutoRepairJob:
    version_id = str(uuid4())
    source = RepairSourceSnapshot(
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        artifact_id=str(uuid4()),
        artifact_version_id=version_id,
        artifact_content_hash="a" * 64,
        artifact_type="RASTER_IMAGE",
        original_branch_id=str(uuid4()),
        original_head_version_id=version_id,
    )
    directive = RepairDirective(
        directive_id=str(uuid4()),
        source_violation_id=str(uuid4()),
        violation_code="BACKGROUND_NOISE",
        dimension="DEFECTS",
        severity="ERROR",
        blocking=False,
        action_type="REGENERATE_REGION",
        target="region:background",
        parameters={"instruction": "remove noise"},
    )
    quality = RepairQualitySnapshot(
        quality_result_id=str(uuid4()),
        artifact_version_id=version_id,
        status="FAIL_REPAIRABLE",
        overall_score=50,
        overall_confidence=0.9,
        hard_violation_codes=(),
        directives=(directive,),
        profile_id="general",
        profile_version=1,
        profile_hash="c" * 64,
    )
    policy = RepairPolicySnapshot(
        policy_id="p",
        version=1,
        max_iterations=2,
        max_total_cost_usd=Decimal("1"),
        minimum_expected_gain=1,
        max_score_regression=1,
        allowed_kinds=frozenset({RepairKind.LOCAL_IMAGE_EDIT}),
    )
    spec = AutoRepairTaskSpec(
        organization_id=source.organization_id,
        project_id=source.project_id,
        task_id=str(uuid4()),
        operation_id=str(uuid4()),
        requested_by="repair-agent",
        source_artifact_version_id=version_id,
        quality_result_id=quality.quality_result_id,
        policy=policy,
    )
    return AutoRepairJob(
        job_id=str(uuid4()),
        spec=spec,
        status=RepairLoopStatus.RUNNING,
        original_source=source,
        working_source=source,
        current_quality=quality,
    )


def test_local_edit_requires_envelope_but_does_not_receive_it() -> None:
    local = _Local()
    executor = CompositeRepairExecutor(
        structural=_Structural(),
        local_image=local,
        generation=_Generation(),
    )
    job = _repair_job()
    plan = RepairPlan(
        iteration=1,
        kind=RepairKind.LOCAL_IMAGE_EDIT,
        directives=job.current_quality.directives,
        expected_gain=10,
        estimated_cost_usd=Decimal("0.20"),
        paid=True,
        reason_codes=("TEST",),
    )
    with pytest.raises(ValueError, match="REPAIR_PAID_RESERVATION_REQUIRED"):
        asyncio.run(
            executor.execute(
                job=job,
                plan=plan,
                repair_branch_id="repair-branch",
                reservation=None,
            )
        )
    candidate = asyncio.run(
        executor.execute(
            job=job,
            plan=plan,
            repair_branch_id="repair-branch",
            reservation=BudgetReservation("reservation", Decimal("0.20")),
        )
    )
    assert candidate.provider_request_id == "request-a"
    assert local.calls == 1
