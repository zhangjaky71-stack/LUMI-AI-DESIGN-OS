from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .definition import AgentDefinition
from .errors import AgentReleaseError
from .release_types import AgentReleaseManifest, AgentReleaseRecord, AgentReleaseStatus


@dataclass(frozen=True, slots=True)
class EvalEvidence:
    passed: bool
    evidence_ref: str


class EvalReleaseGate(Protocol):
    def evaluate(self, definition: AgentDefinition) -> EvalEvidence: ...


class AgentReleaseManager:
    def __init__(self, eval_gate: EvalReleaseGate) -> None:
        self.eval_gate = eval_gate

    def promote(self, manifest: AgentReleaseManifest, definition: AgentDefinition) -> AgentReleaseManifest:
        target = _find(manifest, definition.agent_id, definition.version)
        if target.status != AgentReleaseStatus.CANDIDATE:
            raise AgentReleaseError("only CANDIDATE release can be promoted")
        if target.eval_profile != definition.eval_profile:
            raise AgentReleaseError("release eval profile differs from AgentDefinition")
        evidence = self.eval_gate.evaluate(definition)
        if not evidence.passed:
            raise AgentReleaseError("production promotion blocked by eval release gate")
        releases: list[AgentReleaseRecord] = []
        for row in manifest.releases:
            if row.agent_id == definition.agent_id and row.status == AgentReleaseStatus.PRODUCTION:
                releases.append(replace(row, status=AgentReleaseStatus.DEPRECATED))
            elif row.agent_id == definition.agent_id and row.version == definition.version:
                releases.append(
                    replace(
                        row,
                        status=AgentReleaseStatus.PRODUCTION,
                        eval_status="passed",
                        eval_evidence=evidence.evidence_ref,
                    )
                )
            else:
                releases.append(row)
        aliases = _aliases(manifest)
        aliases.setdefault(definition.agent_id, {})["production"] = definition.version
        return AgentReleaseManifest(
            schema=manifest.schema,
            revision=manifest.revision + 1,
            releases=tuple(releases),
            aliases=aliases,
        )

    def rollback(self, manifest: AgentReleaseManifest, agent_id: str, exact_version: str) -> AgentReleaseManifest:
        target = _find(manifest, agent_id, exact_version)
        if target.status == AgentReleaseStatus.DISABLED:
            raise AgentReleaseError("cannot rollback production alias to DISABLED release")
        if target.eval_status != "passed" or not target.eval_evidence:
            raise AgentReleaseError("rollback target has no passed eval evidence")
        releases: list[AgentReleaseRecord] = []
        for row in manifest.releases:
            if row.agent_id == agent_id and row.status == AgentReleaseStatus.PRODUCTION and row.version != exact_version:
                releases.append(replace(row, status=AgentReleaseStatus.DEPRECATED))
            elif row.agent_id == agent_id and row.version == exact_version:
                releases.append(replace(row, status=AgentReleaseStatus.PRODUCTION))
            else:
                releases.append(row)
        aliases = _aliases(manifest)
        aliases.setdefault(agent_id, {})["production"] = exact_version
        return AgentReleaseManifest(
            schema=manifest.schema,
            revision=manifest.revision + 1,
            releases=tuple(releases),
            aliases=aliases,
        )


def _find(manifest: AgentReleaseManifest, agent_id: str, version: str) -> AgentReleaseRecord:
    row = next((item for item in manifest.releases if item.agent_id == agent_id and item.version == version), None)
    if row is None:
        raise AgentReleaseError(f"release not found: {agent_id}@{version}")
    return row


def _aliases(manifest: AgentReleaseManifest) -> dict[str, dict[str, str]]:
    return {agent_id: dict(values) for agent_id, values in manifest.aliases.items()}
