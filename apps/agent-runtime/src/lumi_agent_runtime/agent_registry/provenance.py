from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .definition import AgentDefinition
from .release_types import AgentReleaseStatus


@dataclass(frozen=True, slots=True)
class ResolvedDependency:
    kind: str
    key: str
    requested: str
    exact_version: str
    content_hash: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class AgentProvenance:
    requested_ref: str
    agent_id: str
    exact_version: str
    release_status: AgentReleaseStatus
    definition_hash: str
    system_prompt_hash: str
    release_manifest_revision: int
    dependencies: tuple[ResolvedDependency, ...]

    @property
    def freeze_hash(self) -> str:
        payload = {
            "requested_ref": self.requested_ref,
            "agent_id": self.agent_id,
            "exact_version": self.exact_version,
            "release_status": self.release_status.value,
            "definition_hash": self.definition_hash,
            "system_prompt_hash": self.system_prompt_hash,
            "release_manifest_revision": self.release_manifest_revision,
            "dependencies": [
                {
                    "kind": item.kind,
                    "key": item.key,
                    "requested": item.requested,
                    "exact_version": item.exact_version,
                    "content_hash": item.content_hash,
                    "source_ref": item.source_ref,
                }
                for item in self.dependencies
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ResolvedAgent:
    definition: AgentDefinition
    provenance: AgentProvenance
