from __future__ import annotations

from pathlib import Path

from lumi_agent_runtime.agent_registry import (
    AgentReleaseManager,
    AgentReleaseStatus,
    EvalEvidence,
    load_definitions,
    load_release_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


class Gate:
    def evaluate(self, definition):
        return EvalEvidence(
            True,
            f"eval://{definition.agent_id}/{definition.version}/release-pass",
        )


class ValidDefinition:
    def validate(self, definition):
        del definition
        return ()


def main() -> int:
    definitions = {
        item.identity: item for item in load_definitions(ROOT / "agents")
    }
    manifest = load_release_manifest(ROOT / "agents/registry.json")
    manager = AgentReleaseManager(Gate(), ValidDefinition())
    candidate = definitions["creative-director@1.2.0"]
    before_hash = definitions["creative-director@1.1.0"].content_hash
    promoted = manager.promote(manifest, candidate)
    assert promoted.aliases["creative-director"]["production"] == "1.2.0"
    assert promoted.revision == 2
    target = next(
        item
        for item in promoted.releases
        if item.agent_id == "creative-director" and item.version == "1.2.0"
    )
    assert target.status == AgentReleaseStatus.PRODUCTION
    rolled = manager.rollback(promoted, "creative-director", "1.1.0")
    assert rolled.aliases["creative-director"]["production"] == "1.1.0"
    assert rolled.revision == 3
    assert definitions["creative-director@1.1.0"].content_hash == before_hash
    print("NODE-30 Agent Registry promotion/rollback integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
