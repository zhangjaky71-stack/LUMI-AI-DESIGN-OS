from __future__ import annotations

import json
from typing import Any

from .errors import DeliveryState, ErrorCategory, ProviderInvocationError
from .models import Capability, ModelOutput, ModelRequest
from .openai_adapter import OpenAIResponsesAdapter

_MAX_TOOLS = 128
_MAX_TOOL_CALLS_PER_MESSAGE = 128


class OpenAIResponsesToolAdapter(OpenAIResponsesAdapter):
    """OpenAI Responses adapter with provider-neutral function-tool semantics.

    Callers supply generic ``tools`` and message/tool-call objects in
    ``ModelRequest.inputs``. Provider-native Responses fields are constructed
    only inside this adapter so Agent Runtime never depends on an OpenAI SDK or
    request schema.
    """

    def validate(self, request: ModelRequest) -> None:
        super().validate(request)
        self._tool_definitions(request)
        self._tool_choice(request)

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        payload = super()._payload(request)
        tools = self._tool_definitions(request)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = self._tool_choice(request)
            parallel = request.inputs.get("parallel_tool_calls")
            if parallel is not None:
                if not isinstance(parallel, bool):
                    raise self._input_error("parallel_tool_calls must be boolean")
                payload["parallel_tool_calls"] = parallel
        return payload

    def _format_input(self, request: ModelRequest) -> str | list[dict[str, Any]]:
        prompt = request.inputs.get("prompt")
        messages = request.inputs.get("messages")
        if isinstance(prompt, str) and prompt.strip() and messages is None:
            return prompt
        if isinstance(messages, list) and messages and prompt is None:
            formatted: list[dict[str, Any]] = []
            seen_call_ids: set[str] = set()
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    raise self._input_error(f"messages[{index}] must be an object")
                role = message.get("role")
                if role in {"developer", "system", "user"}:
                    if set(message) - {"role", "content"}:
                        raise self._input_error(
                            f"messages[{index}] contains provider-native/unknown fields"
                        )
                    content = message.get("content")
                    if not isinstance(content, str):
                        raise self._input_error(
                            f"messages[{index}] requires string content"
                        )
                    formatted.append({"role": role, "content": content})
                    continue
                if role == "assistant":
                    if set(message) - {"role", "content", "tool_calls"}:
                        raise self._input_error(
                            f"messages[{index}] contains provider-native/unknown fields"
                        )
                    content = message.get("content")
                    if content is not None and not isinstance(content, str):
                        raise self._input_error(
                            f"messages[{index}] assistant content must be string or null"
                        )
                    if isinstance(content, str) and content:
                        formatted.append({"role": "assistant", "content": content})
                    tool_calls = message.get("tool_calls", [])
                    if not isinstance(tool_calls, list) or len(tool_calls) > _MAX_TOOL_CALLS_PER_MESSAGE:
                        raise self._input_error(
                            f"messages[{index}] tool_calls must be a bounded list"
                        )
                    if not content and not tool_calls:
                        raise self._input_error(
                            f"messages[{index}] assistant message is empty"
                        )
                    for call_index, call in enumerate(tool_calls):
                        call_id, name, arguments = self._tool_call(
                            call,
                            path=f"messages[{index}].tool_calls[{call_index}]",
                        )
                        if call_id in seen_call_ids:
                            raise self._input_error(f"duplicate tool call id: {call_id}")
                        seen_call_ids.add(call_id)
                        formatted.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": name,
                                "arguments": json.dumps(
                                    arguments,
                                    ensure_ascii=False,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ),
                            }
                        )
                    continue
                if role == "tool":
                    if set(message) - {"role", "tool_call_id", "content"}:
                        raise self._input_error(
                            f"messages[{index}] contains provider-native/unknown fields"
                        )
                    call_id = message.get("tool_call_id")
                    content = message.get("content")
                    if not isinstance(call_id, str) or not call_id or len(call_id) > 512:
                        raise self._input_error(
                            f"messages[{index}] requires tool_call_id"
                        )
                    if not isinstance(content, str):
                        raise self._input_error(
                            f"messages[{index}] tool content must be string"
                        )
                    formatted.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": content,
                        }
                    )
                    continue
                raise self._input_error(f"messages[{index}] has unsupported role")
            return formatted
        raise self._input_error("inputs must contain exactly one of prompt or messages")

    def _outputs(
        self,
        request: ModelRequest,
        payload: dict[str, Any],
    ) -> tuple[tuple[ModelOutput, ...], bool]:
        texts: list[str] = []
        refusals: list[str] = []
        tool_outputs: list[ModelOutput] = []
        raw_output = payload.get("output", [])
        if isinstance(raw_output, list):
            for item in raw_output:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "function_call":
                    call_id = item.get("call_id")
                    name = item.get("name")
                    arguments_text = item.get("arguments")
                    if (
                        not isinstance(call_id, str)
                        or not call_id
                        or not isinstance(name, str)
                        or not name
                        or not isinstance(arguments_text, str)
                    ):
                        raise self._accepted_parse_error(
                            "OpenAI returned an invalid function call"
                        )
                    try:
                        arguments = json.loads(arguments_text)
                    except json.JSONDecodeError as exc:
                        raise self._accepted_parse_error(
                            "OpenAI returned invalid function call arguments"
                        ) from exc
                    if not isinstance(arguments, dict):
                        raise self._accepted_parse_error(
                            "OpenAI function call arguments must decode to an object"
                        )
                    tool_outputs.append(
                        ModelOutput(
                            kind="tool_call",
                            value={"id": call_id, "name": name, "args": arguments},
                            mime_type="application/json",
                        )
                    )
                    continue
                if item_type != "message":
                    continue
                content = item.get("content", [])
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                    if part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                        refusals.append(part["refusal"])

        combined = "".join(texts)
        if request.capability == Capability.LLM_STRUCTURED_OUTPUT and combined:
            if tool_outputs:
                raise self._accepted_parse_error(
                    "structured output response cannot mix function calls"
                )
            try:
                value = json.loads(combined)
            except json.JSONDecodeError as exc:
                raise self._accepted_parse_error(
                    "OpenAI structured output was not valid JSON"
                ) from exc
            return (
                (
                    ModelOutput(
                        kind="json",
                        value=value,
                        mime_type="application/json",
                    ),
                ),
                bool(refusals),
            )

        outputs: list[ModelOutput] = []
        if combined:
            outputs.append(ModelOutput(kind="text", value=combined, mime_type="text/plain"))
        outputs.extend(tool_outputs)
        if refusals:
            outputs.append(
                ModelOutput(
                    kind="refusal",
                    value="\n".join(refusals),
                    mime_type="text/plain",
                )
            )
        return tuple(outputs), bool(refusals)

    def _tool_definitions(self, request: ModelRequest) -> list[dict[str, Any]]:
        raw_tools = request.inputs.get("tools")
        if raw_tools is None:
            return []
        if not isinstance(raw_tools, list) or not 1 <= len(raw_tools) <= _MAX_TOOLS:
            raise self._input_error("tools must contain 1..128 definitions")
        tools: list[dict[str, Any]] = []
        names: set[str] = set()
        for index, raw in enumerate(raw_tools):
            if not isinstance(raw, dict):
                raise self._input_error(f"tools[{index}] must be an object")
            if set(raw) - {"name", "description", "parameters", "strict"}:
                raise self._input_error(f"tools[{index}] contains provider-native/unknown fields")
            name = raw.get("name")
            description = raw.get("description", "")
            parameters = raw.get("parameters")
            strict = raw.get("strict", True)
            if not isinstance(name, str) or not name or len(name) > 128:
                raise self._input_error(f"tools[{index}] has invalid name")
            if name in names:
                raise self._input_error(f"duplicate tool name: {name}")
            names.add(name)
            if not isinstance(description, str) or len(description) > 4096:
                raise self._input_error(f"tools[{index}] has invalid description")
            if not isinstance(parameters, dict):
                raise self._input_error(f"tools[{index}] requires JSON-schema parameters")
            if not isinstance(strict, bool):
                raise self._input_error(f"tools[{index}] strict must be boolean")
            tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                    "strict": strict,
                }
            )
        return tools

    def _tool_choice(self, request: ModelRequest) -> str:
        choice = request.inputs.get("tool_choice", "auto")
        if choice not in {"auto", "none", "required"}:
            raise self._input_error("tool_choice must be auto, none, or required")
        return str(choice)

    def _tool_call(self, raw: Any, *, path: str) -> tuple[str, str, dict[str, Any]]:
        if not isinstance(raw, dict) or set(raw) - {"id", "name", "args"}:
            raise self._input_error(f"{path} must be a provider-neutral tool call")
        call_id = raw.get("id")
        name = raw.get("name")
        arguments = raw.get("args")
        if not isinstance(call_id, str) or not call_id or len(call_id) > 512:
            raise self._input_error(f"{path}.id is invalid")
        if not isinstance(name, str) or not name or len(name) > 128:
            raise self._input_error(f"{path}.name is invalid")
        if not isinstance(arguments, dict):
            raise self._input_error(f"{path}.args must be an object")
        return call_id, name, arguments

    def _accepted_parse_error(self, message: str) -> ProviderInvocationError:
        return ProviderInvocationError(
            ErrorCategory.UNKNOWN,
            message,
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            delivery_state=DeliveryState.ACCEPTED,
        )
