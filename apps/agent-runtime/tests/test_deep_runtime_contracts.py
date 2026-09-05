from __future__ import annotations

import unittest

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepSubagentDefinition,
    DelegationLimits,
)


def child(*, tools=("web.search",), can_delegate=False) -> DeepSubagentDefinition:
    return DeepSubagentDefinition(
        name="researcher",
        description="Research trusted public sources",
        system_prompt="Research the assigned question and return evidence.",
        allowed_tools=tuple(tools),
        model_profile="research-v1",
        can_delegate=can_delegate,
    )


class DeepRuntimeContractTests(unittest.TestCase):
    def test_child_tool_scope_must_be_subset_of_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "DEEP_AGENT_SUBAGENT_TOOL_ESCALATION"):
            DeepAgentDefinition(
                agent_key="designer",
                runtime_version="1.0.0",
                graph_key="deep.designer",
                graph_version="1.0.0",
                agent_config_version="agent-v1",
                system_prompt="Design within the approved project scope.",
                model_profile="design-v1",
                allowed_tools=("web.search",),
                subagents=(child(tools=("web.search", "artifact.query")),),
            )

    def test_definition_hash_changes_when_child_scope_changes(self) -> None:
        first = DeepAgentDefinition(
            agent_key="designer",
            runtime_version="1.0.0",
            graph_key="deep.designer",
            graph_version="1.0.0",
            agent_config_version="agent-v1",
            system_prompt="Design within the approved project scope.",
            model_profile="design-v1",
            allowed_tools=("web.search", "artifact.query"),
            subagents=(child(tools=("web.search",)),),
        )
        second = DeepAgentDefinition(
            agent_key="designer",
            runtime_version="1.0.0",
            graph_key="deep.designer",
            graph_version="1.0.0",
            agent_config_version="agent-v1",
            system_prompt="Design within the approved project scope.",
            model_profile="design-v1",
            allowed_tools=("web.search", "artifact.query"),
            subagents=(child(tools=("artifact.query",)),),
        )
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_delegation_limits_are_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "DEEP_AGENT_MAX_PARALLEL_INVALID"):
            DelegationLimits(max_parallel_subagents=0)
        with self.assertRaisesRegex(ValueError, "DEEP_AGENT_MAX_DEPTH_INVALID"):
            DelegationLimits(max_depth=9)

    def test_binary_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "DEEP_AGENT_BINARY_FORBIDDEN"):
            DeepAgentDefinition(
                agent_key="designer",
                runtime_version="1.0.0",
                graph_key="deep.designer",
                graph_version="1.0.0",
                agent_config_version="agent-v1",
                system_prompt="Design within the approved project scope.",
                model_profile="design-v1",
                allowed_tools=(),
                subagents=(),
                metadata={"secret_blob": b"no"},
            )


if __name__ == "__main__":
    unittest.main()
