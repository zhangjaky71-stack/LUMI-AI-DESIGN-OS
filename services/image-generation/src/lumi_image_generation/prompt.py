from __future__ import annotations

from .model import ConstraintSeverity, ImageGenerationSpec, PromptBlocks


def compile_prompt(spec: ImageGenerationSpec) -> PromptBlocks:
    brand: list[str] = []
    if spec.brand_rule_set_version:
        brand.append(f"brand_rule_set_version={spec.brand_rule_set_version}")

    identity = tuple(
        (
            f"identity_id={item.identity_id};reference_set={item.reference_set_version};"
            f"scenario={item.scenario};severity={item.severity.value}"
        )
        for item in spec.identity_requirements
    )
    negative: list[str] = []
    for item in spec.constraints:
        value = (
            f"constraint_id={item.constraint_id};type={item.constraint_type};"
            f"severity={item.severity.value};snapshot={item.snapshot_hash}"
        )
        if item.severity is ConstraintSeverity.HARD:
            negative.append(value)
        else:
            brand.append(value)
    if spec.output_requirements.transparent_background:
        negative.append("background must remain transparent")

    output = (
        f"{spec.target_width}x{spec.target_height};aspect_ratio={spec.aspect_ratio};"
        f"format={spec.output_requirements.format.value};"
        f"exact={str(spec.output_requirements.exact_dimensions).lower()}"
    )
    return PromptBlocks(
        objective=spec.objective.strip(),
        content=spec.content.strip(),
        visual_direction=spec.visual_direction.strip(),
        brand_constraints=tuple(brand),
        identity_requirements=identity,
        negative_constraints=tuple(negative),
        output_dimensions=output,
        template_version="image-prompt-v1",
    )
