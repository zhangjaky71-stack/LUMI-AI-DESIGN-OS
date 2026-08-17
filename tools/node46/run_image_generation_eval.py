from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from lumi_image_generation import (
    CompositeGenerationValidator,
    ConstraintSeverity,
    GenerationConstraint,
    GenerationMode,
    IdentityRequirement,
    ImageGenerationSpec,
    ImageReference,
    OutputFormat,
    OutputRequirements,
    QualityProfile,
    ReferenceRole,
    ReferenceSource,
)
from lumi_image_generation.image_validation import (
    ImageValidationError,
    validate_provider_image,
)
from lumi_image_generation.model import FetchedImage
from lumi_image_generation.prompt import compile_prompt
from lumi_image_generation.testing import png_bytes
from lumi_image_generation.validation import ValidationStatus
from lumi_image_generation.variants import choose_variants

ROOT = Path(__file__).resolve().parents[2]
ORG = UUID("01910000-0000-7000-8000-000000004601")
PROJECT = UUID("01910000-0000-7000-8000-000000004602")
TASK = UUID("01910000-0000-7000-8000-000000004603")
OP = UUID("01910000-0000-7000-8000-000000004604")
ASSET = UUID("01910000-0000-7000-8000-000000004605")
IDENTITY = UUID("01910000-0000-7000-8000-000000004606")
GIT = "a" * 40


def _spec(case: dict, *, index: int) -> ImageGenerationSpec:
    operation = UUID(int=OP.int + index)
    mode = GenerationMode(case["mode"])
    references = ()
    identities = ()
    brand = None
    constraints = ()
    if mode is GenerationMode.PRODUCT_SCENE:
        references = (
            ImageReference(
                ASSET,
                "b" * 64,
                ReferenceRole.IDENTITY,
                ReferenceSource.USER_EXPLICIT,
            ),
        )
        identities = (
            IdentityRequirement(
                IDENTITY,
                "identity-set-v1",
                ConstraintSeverity.HARD,
                "product-packshot",
            ),
        )
    if mode is GenerationMode.STYLE_REFERENCE:
        references = (
            ImageReference(
                ASSET,
                "b" * 64,
                ReferenceRole.STYLE,
                ReferenceSource.USER_EXPLICIT,
            ),
        )
        brand = "brand-rules-v1"
        constraints = (
            GenerationConstraint(
                "brand-logo-clearspace",
                "BRAND_LOGO_CLEARSPACE",
                ConstraintSeverity.HARD,
                "c" * 64,
            ),
        )
    transparent = mode is GenerationMode.TRANSPARENT_ASSET
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=operation,
        purpose="node46 deterministic control-plane eval",
        mode=mode,
        prompt_compilation_ref="eval:node46-v1",
        objective=case.get("objective", "Create a production design asset"),
        content=case.get("content", "Preserve all hard requirements"),
        visual_direction="minimal editorial composition",
        aspect_ratio=f"{case['width']}:{case['height']}",
        target_width=case["width"],
        target_height=case["height"],
        variant_count=4 if case["id"] == "budget-fallback" else 1,
        references=references,
        identity_requirements=identities,
        brand_rule_set_version=brand,
        constraints=constraints,
        quality_profile=QualityProfile.BALANCED,
        budget_limit_usd=Decimal("0.025") if case["id"] == "budget-fallback" else Decimal("1"),
        output_requirements=OutputRequirements(
            OutputFormat.PNG,
            transparent_background=transparent,
            exact_dimensions=True,
        ),
        code_git_sha=GIT,
        agent_run_id=TASK,
        agent_version="eval/1.0.0",
        recipe_version="node46-eval/1.0.0",
        skill_versions={"image-generation": "1.0.0"},
        seed=42,
    )


async def _run() -> None:
    fixture = json.loads(
        (ROOT / "evals/node46/image-generation-fixtures.json").read_text(encoding="utf-8")
    )
    assert fixture["schema_version"] == "lumi.image-generation-eval/1.0"
    assert len(fixture["cases"]) == 7

    for index, case in enumerate(fixture["cases"], start=1):
        spec = _spec(case, index=index)
        prompt = compile_prompt(spec)
        assert str(spec.target_width) in prompt.output_dimensions
        assert str(spec.target_height) in prompt.output_dimensions

        if case["id"] == "chinese-poster":
            assert "高级咖啡促销海报" in prompt.objective
            assert "新品拿铁" in prompt.content
            assert len(prompt.prompt_hash) == 64
        elif case["id"] == "product-scene":
            assert spec.references[0].role is ReferenceRole.IDENTITY
            assert spec.identity_requirements[0].severity is ConstraintSeverity.HARD
        elif case["id"] == "brand-identity-hard-gate":
            validator = CompositeGenerationValidator()
            content = png_bytes(spec.target_width, spec.target_height)
            from lumi_image_generation.model import StoredImage, ValidatedImage

            image = ValidatedImage(
                content,
                "image/png",
                spec.target_width,
                spec.target_height,
                "d" * 64,
                True,
            )
            stored = StoredImage(
                "eval",
                "eval/brand.png",
                "image/png",
                spec.target_width,
                spec.target_height,
                len(content),
                "d" * 64,
            )
            result = await validator.validate(
                spec=spec,
                candidate_id=UUID(int=OP.int + 100),
                image=image,
                stored=stored,
                references=(),
            )
            assert result.hard_failed
            assert any(item.status is ValidationStatus.UNAVAILABLE for item in result.findings)
        elif case["id"] in {"landscape-16-9", "portrait-9-16"}:
            content = png_bytes(spec.target_width, spec.target_height)
            image = validate_provider_image(
                FetchedImage("fixture", content, "image/png"), spec
            )
            assert (image.width, image.height) == (spec.target_width, spec.target_height)
        elif case["id"] == "transparent-asset":
            opaque = png_bytes(spec.target_width, spec.target_height, alpha=False)
            try:
                validate_provider_image(FetchedImage("fixture", opaque, "image/png"), spec)
            except ImageValidationError as exc:
                assert str(exc) == "IMAGE_OUTPUT_ALPHA_REQUIRED"
            else:
                raise AssertionError("opaque output passed transparent requirement")
            alpha = png_bytes(spec.target_width, spec.target_height, alpha=True)
            assert validate_provider_image(
                FetchedImage("fixture", alpha, "image/png"), spec
            ).has_alpha
        elif case["id"] == "budget-fallback":
            decision = choose_variants(
                spec,
                estimated_cost_per_variant_usd=Decimal("0.01"),
            )
            assert decision.requested_count == 4
            assert decision.selected_count == 2
            assert "HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED" in decision.reason_codes
            changed = replace(spec, budget_limit_usd=Decimal("1"))
            assert choose_variants(
                changed,
                estimated_cost_per_variant_usd=Decimal("0.01"),
            ).selected_count == 4

    print("NODE46_IMAGE_GENERATION_EVAL_PASS cases=7")
    print("visual_quality_claimed=false")


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
