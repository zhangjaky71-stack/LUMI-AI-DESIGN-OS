from __future__ import annotations

from .model import ImageGenerationSpec, PromptBlocks


def compile_prompt(spec: ImageGenerationSpec) -> PromptBlocks:
    """Compile business intent into provider-neutral blocks.

    Provider adapters may format these blocks for a specific API, but must not receive an
    unstructured user prompt and silently reinterpret hard requirements.
    """

    brand_constraints: list[str] = []
    if spec.brand_rule_set_version:
        brand_constraints.append(f"brand_rule_set_version={spec.brand_rule_set_version}")

    identity_requirements = tuple(
        (
            f"identity_id={item.identity_id}; reference_set={item.reference_set_version}; "
            f"scenario={item.scenario}; severity={item.severity}"
        )
        for item in spec.identity_requirements
    )

    negative_constraints: list[str] = []
    for constraint in spec.constraints:
        statement = (
            f"constraint_id={constraint.constraint_id}; type={constraint.constraint_type}; "
            f"severity={constraint.severity}"
        )
        if constraint.severity == "HARD":
            negative_constraints.append(statement)
        else:
            brand_constraints.append(statement)

    if spec.output_requirements.transparent_background:
        negative_constraints.append("background must remain transparent")

    output_dimensions = (
        f"{spec.target_width}x{spec.target_height}; aspect_ratio={spec.aspect_ratio}; "
        f"format={spec.output_requirements.format}; exact={spec.output_requirements.exact_dimensions}"
    )

    return PromptBlocks(
        objective=spec.objective.strip(),
        content=spec.content.strip(),
        visual_direction=spec.visual_direction.strip(),
        brand_constraints=tuple(brand_constraints),
        identity_requirements=identity_requirements,
        negative_constraints=tuple(negative_constraints),
        output_dimensions=output_dimensions,
        template_version="image-prompt-v1",
    )
