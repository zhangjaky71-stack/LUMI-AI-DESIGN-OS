from __future__ import annotations

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentDefinition, DelegationLimits

from .provenance import ResolvedAgent


def to_deep_agent_definition(resolved: ResolvedAgent) -> DeepAgentDefinition:
    definition = resolved.definition
    provenance = resolved.provenance
    return DeepAgentDefinition(
        agent_key=definition.agent_id,
        runtime_version=definition.version,
        graph_key=f"agent.{definition.agent_id}",
        graph_version=definition.version,
        agent_config_version=f"registry-{definition.version}",
        system_prompt=definition.system_prompt,
        model_profile=definition.model_policy,
        allowed_tools=tuple(item.name for item in definition.tools),
        subagents=(),
        delegation=DelegationLimits(
            max_depth=1,
            max_total_subagent_calls=0,
            max_parallel_subagents=1,
            max_children_per_agent=0,
        ),
        max_steps=definition.max_steps,
        planning_enabled=True,
        virtual_files_enabled=True,
        metadata={
            "agent_registry_definition_hash": definition.content_hash,
            "agent_registry_provenance_hash": provenance.freeze_hash,
            "agent_registry_requested_ref": provenance.requested_ref,
            "output_schema": definition.output_schema,
            "eval_profile": definition.eval_profile,
            "skills": [item.ref for item in definition.skills],
            "context_policy": definition.context_policy,
            "budget_policy": definition.budget_policy,
        },
    )
