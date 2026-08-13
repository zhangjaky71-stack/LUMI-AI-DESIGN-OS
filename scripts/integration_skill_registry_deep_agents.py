from __future__ import annotations

import asyncio
import inspect
from importlib import import_module
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    DelegationLimits,
)
from lumi_agent_runtime.deep_runtime.providers import (
    mark_backend_bound,
    mark_model_gateway_bound,
)
from lumi_agent_runtime.deep_runtime.runtime_factory import (
    BoundedDeepAgentRuntimeFactory,
)
from lumi_agent_runtime.skill_registry import (
    DeepAgentsSkillBundle,
    SkillAwareDeepAgentCompiler,
    SkillExecutionContext,
    SkillRegistry,
    inject_skill_files,
    load_release_manifest,
    load_skills,
)


class FinalAnswerModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "lumi-node31-skill-test-model"

    def bind_tools(self, tools, **kwargs):
        del tools, kwargs
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content="NODE31_SKILL_OK")
                )
            ]
        )


class Models:
    def __init__(self) -> None:
        self.model = mark_model_gateway_bound(FinalAnswerModel())

    async def model_for_root(self, *, model_profile, context):
        del model_profile, context
        return self.model

    async def model_for_subagent(self, *, definition, context):
        del definition, context
        return self.model


class NoExternalTools:
    async def tools_for_root(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()

    async def tools_for_subagent(self, *, context, allowed_tools):
        del context
        assert allowed_tools == ()
        return ()


class StateBackendProvider:
    async def backend_for_run(self, *, context, virtual_files_enabled):
        del context
        assert virtual_files_enabled is True
        backend_type = getattr(
            import_module("deepagents.backends"),
            "StateBackend",
        )

        def factory(runtime):
            parameters = inspect.signature(backend_type).parameters
            return backend_type() if len(parameters) == 0 else backend_type(runtime)

        return mark_backend_bound(factory)


class Checkpointers:
    async def checkpointer_for_run(self, *, context):
        del context
        return InMemorySaver()


async def main_async() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    skill_registry = SkillRegistry(
        load_skills(root / "skills"),
        load_release_manifest(root / "skills/registry.json"),
    )
    pack = skill_registry.resolve_pack(
        ("brief-normalization@^1",),
        SkillExecutionContext(
            agent_id="creative-director",
            allowed_tools=frozenset(),
            granted_permissions=frozenset(),
            available_capabilities=frozenset(),
        ),
    )
    bundle = DeepAgentsSkillBundle(pack)
    definition = DeepAgentDefinition(
        agent_key="creative-director",
        runtime_version="1.0.0",
        graph_key="skill.acceptance",
        graph_version="1.0.0",
        agent_config_version="agent-skill-v1",
        system_prompt=(
            "Return the deterministic acceptance marker. "
            "Do not call tools or subagents."
        ),
        model_profile="node22-test-profile",
        allowed_tools=(),
        subagents=(),
        delegation=DelegationLimits(
            max_depth=1,
            max_total_subagent_calls=1,
            max_parallel_subagents=1,
            max_children_per_agent=1,
        ),
        max_steps=12,
        virtual_files_enabled=True,
    )
    context = DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=None,
        operation_id=uuid4(),
        actor_id="node31-skill-acceptance",
        root_agent="creative-director",
        granted_permissions=frozenset({"agent:execute"}),
        allowed_tools=(),
    )
    compiler = SkillAwareDeepAgentCompiler(
        BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=NoExternalTools(),
            backends=StateBackendProvider(),
            checkpointers=Checkpointers(),
        )
    )
    compiled = await compiler.compile(
        definition,
        context=context,
        bundle=bundle,
    )
    assert compiled.graph_definition.metadata["skill_pack_freeze_hash"] == pack.freeze_hash
    assert compiled.graph_definition.metadata["resolved_skills"] == [
        {
            "id": "brief-normalization",
            "version": "1.0.0",
            "hash": pack.skills[0].definition.content_hash,
        }
    ]
    input_state = inject_skill_files(
        {
            "messages": [
                HumanMessage(content="Return the acceptance marker.")
            ]
        },
        bundle,
    )
    assert "/skills/brief-normalization/SKILL.md" in input_state["files"]
    result = await compiled.compiled_graph.ainvoke(
        input_state,
        config={
            "configurable": {
                "thread_id": f"node31-{context.agent_run_id}"
            }
        },
    )
    messages = result.get("messages") if isinstance(result, dict) else None
    assert isinstance(messages, list) and messages
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "NODE31_SKILL_OK"


def main() -> int:
    asyncio.run(main_async())
    print("NODE-31 Skill Registry -> current Deep Agents integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
