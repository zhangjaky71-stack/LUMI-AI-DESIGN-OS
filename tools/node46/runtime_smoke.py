from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from lumi_image_generation import (
    CompositeGenerationValidator,
    GenerationMode,
    ImageGenerationPipeline,
    ImageGenerationSpec,
    InMemoryGenerationRepository,
    JobStatus,
    OutputRequirements,
    QualityProfile,
)
from lumi_image_generation.testing import (
    FakeGateway,
    FixtureFetcher,
    MemoryArtifacts,
    MemoryCosts,
    MemoryEvents,
    MemoryStorage,
    MemoryWork,
    StaticReferenceAuthorizer,
)

ORG = UUID("01910000-0000-7000-8000-000000004611")
PROJECT = UUID("01910000-0000-7000-8000-000000004612")
TASK = UUID("01910000-0000-7000-8000-000000004613")
OP = UUID("01910000-0000-7000-8000-000000004614")
NOW = "2026-08-17T13:00:00+00:00"


async def run() -> None:
    repository = InMemoryGenerationRepository()
    gateway = FakeGateway(cost="0.01")
    artifacts = MemoryArtifacts()
    costs = MemoryCosts()
    events = MemoryEvents()
    work = MemoryWork()
    pipeline = ImageGenerationPipeline(
        repository=repository,
        references=StaticReferenceAuthorizer(),
        gateway=gateway,
        output_fetcher=FixtureFetcher(32, 32),
        storage=MemoryStorage(),
        validator=CompositeGenerationValidator(),
        artifacts=artifacts,
        costs=costs,
        events=events,
        work=work,
    )
    spec = ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OP,
        purpose="runtime smoke",
        mode=GenerationMode.TEXT_TO_IMAGE,
        prompt_compilation_ref="smoke:v1",
        objective="Generate a small deterministic image",
        content="black square",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=32,
        target_height=32,
        variant_count=3,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile=QualityProfile.BALANCED,
        budget_limit_usd=Decimal("0.025"),
        output_requirements=OutputRequirements(),
        code_git_sha="a" * 40,
        agent_run_id=TASK,
        agent_version="smoke/1.0.0",
        recipe_version="smoke/1.0.0",
        skill_versions={"image-generation": "1.0.0"},
        seed=7,
    )
    queued = await pipeline.submit(spec, now=NOW)
    assert queued.status is JobStatus.QUEUED
    assert gateway.invocations == 0
    assert queued.variant_decision.selected_count == 2
    completed = await pipeline.execute(
        organization_id=ORG,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert completed.status is JobStatus.COMPLETED
    assert len(artifacts.values) == 2
    assert len(costs.values) == 2
    assert events.values[0][0] == "generation.started"
    assert events.values[-1][0] == "generation.completed"
    print("NODE46_IMAGE_GENERATION_RUNTIME_SMOKE_PASS")
    print(
        "queued=202-style selected_variants=2 "
        f"provider_invocations={gateway.invocations} artifacts={len(artifacts.values)}"
    )


if __name__ == "__main__":
    asyncio.run(run())
