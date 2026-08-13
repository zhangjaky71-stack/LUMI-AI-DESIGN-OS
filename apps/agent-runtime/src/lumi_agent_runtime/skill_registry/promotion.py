from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .contracts import (
    SkillDefinition,
    SkillReleaseManifest,
    SkillReleaseRecord,
    SkillReleaseStatus,
)
from .definition_validator import SkillDefinitionValidator
from .errors import SkillReleaseError


@dataclass(frozen=True, slots=True)
class SkillEvalEvidence:
    passed: bool
    evidence_ref: str


class SkillEvalGate(Protocol):
    def evaluate(self, definition: SkillDefinition) -> SkillEvalEvidence: ...


class SkillPromotionManager:
    def __init__(
        self,
        *,
        validator: SkillDefinitionValidator,
        eval_gate: SkillEvalGate,
    ) -> None:
        self.validator = validator
        self.eval_gate = eval_gate

    def promote(
        self,
        manifest: SkillReleaseManifest,
        definition: SkillDefinition,
    ) -> SkillReleaseManifest:
        target = _release(manifest, definition.skill_id, definition.version)
        if target.status != SkillReleaseStatus.CANDIDATE:
            raise SkillReleaseError("only CANDIDATE Skill can be promoted")
        if target.eval_profile != definition.eval_profile:
            raise SkillReleaseError("Skill release eval profile mismatch")
        self.validator.validate(definition)
        evidence = self.eval_gate.evaluate(definition)
        if not evidence.passed or not evidence.evidence_ref:
            raise SkillReleaseError(
                "Skill production promotion blocked by eval gate"
            )

        releases: list[SkillReleaseRecord] = []
        for row in manifest.releases:
            if (
                row.skill_id == definition.skill_id
                and row.status == SkillReleaseStatus.PRODUCTION
            ):
                releases.append(
                    replace(row, status=SkillReleaseStatus.DEPRECATED)
                )
            elif (
                row.skill_id == definition.skill_id
                and row.version == definition.version
            ):
                releases.append(
                    replace(
                        row,
                        status=SkillReleaseStatus.PRODUCTION,
                        eval_status="passed",
                        eval_evidence=evidence.evidence_ref,
                    )
                )
            else:
                releases.append(row)
        aliases = {
            skill_id: dict(values)
            for skill_id, values in manifest.aliases.items()
        }
        aliases.setdefault(definition.skill_id, {})[
            "production"
        ] = definition.version
        return SkillReleaseManifest(
            schema=manifest.schema,
            revision=manifest.revision + 1,
            releases=tuple(releases),
            aliases=aliases,
        )


def _release(
    manifest: SkillReleaseManifest,
    skill_id: str,
    version: str,
) -> SkillReleaseRecord:
    row = next(
        (
            item
            for item in manifest.releases
            if item.skill_id == skill_id and item.version == version
        ),
        None,
    )
    if row is None:
        raise SkillReleaseError(
            f"Skill release not found: {skill_id}@{version}"
        )
    return row
