from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .contracts import (
    CompiledRecipe,
    RecipeDefinition,
    RecipeReleaseManifest,
    RecipeReleaseRecord,
    RecipeReleaseStatus,
)
from .errors import RecipeReleaseError


class RecipeCompileValidator(Protocol):
    def compile(self, requested_ref: str) -> CompiledRecipe: ...


@dataclass(frozen=True, slots=True)
class RecipeEvalEvidence:
    passed: bool
    evidence_ref: str


class RecipeEvalGate(Protocol):
    def evaluate(self, definition: RecipeDefinition) -> RecipeEvalEvidence: ...


class RecipeDefinitionValidator:
    def __init__(
        self,
        *,
        compiler: RecipeCompileValidator,
        known_eval_profiles: frozenset[str],
    ) -> None:
        self.compiler = compiler
        self.known_eval_profiles = known_eval_profiles

    def validate(self, definition: RecipeDefinition) -> CompiledRecipe:
        eval_profile = definition.metadata.get("eval_profile")
        if not isinstance(eval_profile, str) or eval_profile not in self.known_eval_profiles:
            raise RecipeReleaseError(
                f"Recipe eval profile is not registered: {definition.identity}"
            )
        compiled = self.compiler.compile(definition.identity)
        if compiled.definition.content_hash != definition.content_hash:
            raise RecipeReleaseError(
                f"Recipe compiler resolved different content: {definition.identity}"
            )
        return compiled


class RecipePromotionManager:
    def __init__(
        self,
        *,
        validator: RecipeDefinitionValidator,
        eval_gate: RecipeEvalGate,
    ) -> None:
        self.validator = validator
        self.eval_gate = eval_gate

    def promote(
        self,
        manifest: RecipeReleaseManifest,
        definition: RecipeDefinition,
    ) -> RecipeReleaseManifest:
        target = _release(manifest, definition.recipe_id, definition.version)
        if target.status != RecipeReleaseStatus.CANDIDATE:
            raise RecipeReleaseError("only CANDIDATE Recipe can be promoted")
        declared_profile = definition.metadata.get("eval_profile")
        if target.eval_profile != declared_profile:
            raise RecipeReleaseError("Recipe release eval profile mismatch")
        self.validator.validate(definition)
        evidence = self.eval_gate.evaluate(definition)
        if not evidence.passed or not evidence.evidence_ref:
            raise RecipeReleaseError(
                "Recipe production promotion blocked by benchmark/eval gate"
            )

        releases: list[RecipeReleaseRecord] = []
        for row in manifest.releases:
            if (
                row.recipe_id == definition.recipe_id
                and row.status == RecipeReleaseStatus.PRODUCTION
            ):
                releases.append(
                    replace(row, status=RecipeReleaseStatus.DEPRECATED)
                )
            elif (
                row.recipe_id == definition.recipe_id
                and row.version == definition.version
            ):
                releases.append(
                    replace(
                        row,
                        status=RecipeReleaseStatus.PRODUCTION,
                        eval_status="passed",
                        eval_evidence=evidence.evidence_ref,
                    )
                )
            else:
                releases.append(row)
        aliases = {
            recipe_id: dict(values)
            for recipe_id, values in manifest.aliases.items()
        }
        aliases.setdefault(definition.recipe_id, {})[
            "production"
        ] = definition.version
        return RecipeReleaseManifest(
            schema=manifest.schema,
            revision=manifest.revision + 1,
            releases=tuple(releases),
            aliases=aliases,
        )


def _release(
    manifest: RecipeReleaseManifest,
    recipe_id: str,
    version: str,
) -> RecipeReleaseRecord:
    row = next(
        (
            item
            for item in manifest.releases
            if item.recipe_id == recipe_id and item.version == version
        ),
        None,
    )
    if row is None:
        raise RecipeReleaseError(
            f"Recipe release not found: {recipe_id}@{version}"
        )
    return row
