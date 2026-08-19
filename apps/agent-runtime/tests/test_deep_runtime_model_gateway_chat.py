from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from lumi_model_gateway import (
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelResult,
    ResultStatus,
    Timing,
    Usage,
)

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    SubagentInvocationContext,
)
from lumi_agent_runtime.deep_runtime.errors import DeepAgentModelBoundaryError
from lumi_agent_runtime.deep_runtime.model_gateway_chat import (
    HttpProfileModelProvider,
    ModelGatewayChatModel,
)

_SECRET = "x" * 32


def _model() -> ModelGatewayChatModel:
    return ModelGatewayChatModel(
        base_url="http://model-gateway.test.internal:8080",
        auth_secret=_SECRET,
        model_profile="reasoning.high",
        organization_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        agent_run_id=uuid4(),
        parent_operation_id=uuid4(),
        trace_id="trace-test",
        budget_limit_usd="1.25",
    )


def _result(*outputs: ModelOutput) -> ModelResult:
    return ModelResult(
        status=ResultStatus.SUCCEEDED,
        provider="openai",
        model="test-model",
        provider_request_id="resp_test",
        outputs=tuple(outputs),
        usage=Usage(input_tokens=10, output_tokens=4, total_tokens=14),
        timing=Timing(total_ms=12),
        cost=CostEstimate(
            amount_usd=Decimal("0.0012"),
            confidence=CostConfidence.EXACT,
            price_snapshot_id="test-price",
        ),
        finish_reason="completed",
    )


class ModelGatewayChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_turn_reuses_operation_id_and_changed_turn_gets_new_id(self) -> None:
        model = _model()
        invoke = AsyncMock(return_value=_result(ModelOutput(kind="text", value="ok")))
        with patch(
            "lumi_agent_runtime.deep_runtime.model_gateway_chat.HttpModelGatewayClient.invoke",
            new=invoke,
        ):
            await model._agenerate([HumanMessage(content="hello")])
            await model._agenerate([HumanMessage(content="hello")])
            await model._agenerate(
                [HumanMessage(content="hello"), AIMessage(content="next")]
            )

        first = invoke.await_args_list[0].args[0]
        second = invoke.await_args_list[1].args[0]
        third = invoke.await_args_list[2].args[0]
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertNotEqual(first.operation_id, third.operation_id)
        self.assertNotEqual(first.operation_id, model.parent_operation_id)
        self.assertEqual(first.constraints["model_profile"], "reasoning.high")
        self.assertEqual(first.budget_limit_usd, Decimal("1.25"))

    async def test_tools_and_tool_results_stay_provider_neutral(self) -> None:
        model = _model().bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Look up a value",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
        )
        invoke = AsyncMock(
            return_value=_result(
                ModelOutput(
                    kind="tool_call",
                    value={"id": "call_1", "name": "lookup", "args": {"query": "x"}},
                )
            )
        )
        with patch(
            "lumi_agent_runtime.deep_runtime.model_gateway_chat.HttpModelGatewayClient.invoke",
            new=invoke,
        ):
            chat_result = await model._agenerate([HumanMessage(content="find x")])

        request = invoke.await_args.args[0]
        self.assertEqual(request.inputs["tools"][0]["name"], "lookup")
        self.assertNotIn("function", request.inputs["tools"][0])
        self.assertEqual(request.inputs["tool_choice"], "auto")
        ai = chat_result.generations[0].message
        self.assertEqual(ai.tool_calls[0]["id"], "call_1")
        self.assertEqual(ai.tool_calls[0]["name"], "lookup")
        self.assertEqual(ai.tool_calls[0]["args"], {"query": "x"})

        second_invoke = AsyncMock(return_value=_result(ModelOutput(kind="text", value="done")))
        with patch(
            "lumi_agent_runtime.deep_runtime.model_gateway_chat.HttpModelGatewayClient.invoke",
            new=second_invoke,
        ):
            await model._agenerate(
                [
                    HumanMessage(content="find x"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"id": "call_1", "name": "lookup", "args": {"query": "x"}}
                        ],
                    ),
                    ToolMessage(content="value-x", tool_call_id="call_1"),
                ]
            )
        second_request = second_invoke.await_args.args[0]
        self.assertEqual(
            second_request.inputs["messages"][-1],
            {"role": "tool", "tool_call_id": "call_1", "content": "value-x"},
        )

    async def test_secret_is_not_serialized_or_repr_exposed(self) -> None:
        model = _model()
        self.assertNotIn(_SECRET, repr(model))
        self.assertNotIn("auth_secret", model.model_dump())
        self.assertTrue(model._lumi_model_gateway_bound)

    async def test_profile_provider_propagates_root_and_subagent_budget(self) -> None:
        provider = HttpProfileModelProvider(
            base_url="http://model-gateway.test.internal:8080",
            auth_secret=_SECRET,
        )
        shared = dict(
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
            task_id=uuid4(),
            operation_id=uuid4(),
            actor_id="agent-test",
            root_agent="designer",
            granted_permissions=frozenset({"project.read"}),
            allowed_tools=("asset.search",),
            trace_id="trace-budget",
            budget_limit_usd="2.50",
        )
        root = DeepAgentInvocationContext(**shared)
        root_model = await provider.model_for_root(
            model_profile="reasoning.high",
            context=root,
        )
        self.assertEqual(root_model.budget_limit_usd, "2.50")

        sub = SubagentInvocationContext(
            organization_id=root.organization_id,
            project_id=root.project_id,
            agent_run_id=root.agent_run_id,
            task_id=root.task_id,
            operation_id=root.operation_id,
            actor_id=root.actor_id,
            root_agent=root.root_agent,
            subagent_name="researcher",
            depth=1,
            granted_permissions=root.granted_permissions,
            parent_allowed_tools=root.allowed_tools,
            allowed_tools=root.allowed_tools,
            trace_id=root.trace_id,
            budget_limit_usd=root.budget_limit_usd,
        )
        sub_model = await provider.model_for_subagent(
            definition=type("Definition", (), {"model_profile": "reasoning.fast"})(),
            context=sub,
        )
        self.assertEqual(sub_model.budget_limit_usd, "2.50")
        self.assertEqual(sub_model.model_profile, "reasoning.fast")

    def test_missing_internal_gateway_config_fails_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DeepAgentModelBoundaryError):
                HttpProfileModelProvider.from_env()

    async def test_refusal_only_result_fails_closed(self) -> None:
        model = _model()
        invoke = AsyncMock(return_value=_result(ModelOutput(kind="refusal", value="no")))
        with patch(
            "lumi_agent_runtime.deep_runtime.model_gateway_chat.HttpModelGatewayClient.invoke",
            new=invoke,
        ):
            with self.assertRaises(DeepAgentModelBoundaryError):
                await model._agenerate([HumanMessage(content="hello")])


if __name__ == "__main__":
    unittest.main()
