from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    DeepSubagentDefinition,
    DelegationLimits,
)
from lumi_agent_runtime.deep_runtime.errors import (
    DeepAgentDelegationDeniedError,
    DeepAgentModelBoundaryError,
    DeepAgentToolScopeError,
)
from lumi_agent_runtime.deep_runtime.runtime_factory import BoundedDeepAgentRuntimeFactory


class MarkedModel:
    _lumi_model_gateway_bound = True


class MarkedTool:
    _lumi_tool_gateway_bound = True

    def __init__(self, name: str) -> None:
        self._lumi_tool_name = name


class MarkedBackend:
    _lumi_backend_bound = True


class Models:
    def __init__(self, *, marked: bool = True) -> None:
        self.marked = marked

    async def model_for_root(self, *, model_profile, context):
        del model_profile, context
        return MarkedModel() if self.marked else object()

    async def model_for_subagent(self, *, definition, context):
        del definition, context
        return MarkedModel() if self.marked else object()


class Tools:
    def __init__(self, *, extra: str | None = None) -> None:
        self.extra = extra

    async def tools_for_root(self, *, context, allowed_tools):
        del context
        names = list(allowed_tools)
        if self.extra:
            names.append(self.extra)
        return tuple(MarkedTool(name) for name in names)

    async def tools_for_subagent(self, *, context, allowed_tools):
        del context
        return tuple(MarkedTool(name) for name in allowed_tools)


class Backends:
    async def backend_for_run(self, *, context, virtual_files_enabled):
        del context, virtual_files_enabled
        return MarkedBackend()


class Checkpointers:
    async def checkpointer_for_run(self, *, context):
        del context
        return object()


class FakeCompiled:
    def __init__(self, checkpointer) -> None:
        self.checkpointer = checkpointer
        self.configs = []

    async def ainvoke(self, value, config=None, **kwargs):
        del value, kwargs
        self.configs.append(dict(config or {}))
        return {"ok": True}

    async def aget_state(self, config, **kwargs):
        del kwargs
        return {"config": config}


def fake_create_deep_agent(
    *,
    model,
    tools,
    system_prompt,
    subagents,
    backend,
    checkpointer,
    name=None,
):
    assert model is not None
    assert isinstance(tools, list)
    assert system_prompt
    assert isinstance(subagents, list)
    assert backend is not None
    del name
    return FakeCompiled(checkpointer)


def definition(*, nested: bool = False) -> DeepAgentDefinition:
    return DeepAgentDefinition(
        agent_key="designer",
        runtime_version="1.0.0",
        graph_key="deep.designer",
        graph_version="1.0.0",
        agent_config_version="agent-v1",
        system_prompt="Use only approved LUMI tools and return a concise design plan.",
        model_profile="design-v1",
        allowed_tools=("web.search", "artifact.query"),
        subagents=(
            DeepSubagentDefinition(
                name="researcher",
                description="Research public evidence",
                system_prompt="Research only with your approved scope.",
                allowed_tools=("web.search",),
                model_profile="research-v1",
                can_delegate=nested,
            ),
        ),
        delegation=DelegationLimits(max_depth=2, max_parallel_subagents=2),
        max_steps=20,
    )


def context() -> DeepAgentInvocationContext:
    return DeepAgentInvocationContext(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="user-1",
        root_agent="designer",
        granted_permissions=frozenset({"tools:web.search", "artifacts:read"}),
        allowed_tools=("web.search", "artifact.query"),
    )


class DeepRuntimeFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_compiles_exact_root_and_child_tool_scopes(self) -> None:
        factory = BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=Tools(),
            backends=Backends(),
            checkpointers=Checkpointers(),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
            return_value=fake_create_deep_agent,
        ):
            compiled = await factory.compile(definition(), context=context())
        self.assertEqual(compiled.effective_root_tools, ("web.search", "artifact.query"))
        self.assertEqual(compiled.subagent_tools, {"researcher": ("web.search",)})
        self.assertEqual(compiled.graph_definition.graph_key, "deep.designer")
        self.assertEqual(compiled.graph_definition.metadata["recursion_limit"], 20)

    async def test_unmarked_model_is_rejected(self) -> None:
        factory = BoundedDeepAgentRuntimeFactory(
            models=Models(marked=False),
            tools=Tools(),
            backends=Backends(),
            checkpointers=Checkpointers(),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
            return_value=fake_create_deep_agent,
        ), self.assertRaises(DeepAgentModelBoundaryError):
            await factory.compile(definition(), context=context())

    async def test_tool_provider_cannot_expand_scope(self) -> None:
        factory = BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=Tools(extra="project.query"),
            backends=Backends(),
            checkpointers=Checkpointers(),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
            return_value=fake_create_deep_agent,
        ), self.assertRaises(DeepAgentToolScopeError):
            await factory.compile(definition(), context=context())

    async def test_nested_subagent_delegation_is_fail_closed_in_p0(self) -> None:
        factory = BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=Tools(),
            backends=Backends(),
            checkpointers=Checkpointers(),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
            return_value=fake_create_deep_agent,
        ), self.assertRaises(DeepAgentDelegationDeniedError):
            await factory.compile(definition(nested=True), context=context())

    async def test_compiled_graph_limits_cannot_be_widened_by_caller(self) -> None:
        factory = BoundedDeepAgentRuntimeFactory(
            models=Models(),
            tools=Tools(),
            backends=Backends(),
            checkpointers=Checkpointers(),
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.factory._load_create_deep_agent",
            return_value=fake_create_deep_agent,
        ):
            compiled = await factory.compile(definition(), context=context())
        await compiled.compiled_graph.ainvoke(
            {},
            config={"recursion_limit": 999, "max_concurrency": 99},
        )
        inner = compiled.compiled_graph._graph
        self.assertEqual(inner.configs[-1]["recursion_limit"], 20)
        self.assertEqual(inner.configs[-1]["max_concurrency"], 2)


if __name__ == "__main__":
    unittest.main()
