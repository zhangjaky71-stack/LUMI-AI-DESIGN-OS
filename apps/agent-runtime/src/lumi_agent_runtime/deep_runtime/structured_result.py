from __future__ import annotations

import json
from typing import Any

from .contracts import AgentTaskResult, AgentTaskStatus, DeepAgentInvocationContext
from .errors import DeepAgentStructuredOutputError
from .ports import StructuredOutputRepairer

AGENT_TASK_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status",
        "summary",
        "decisions",
        "artifact_refs",
        "knowledge_refs",
        "proposed_operations",
        "open_questions",
        "confidence",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": [item.value for item in AgentTaskStatus],
        },
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "artifact_refs": {"type": "array", "items": {"type": "string"}},
        "knowledge_refs": {"type": "array", "items": {"type": "string"}},
        "proposed_operations": {"type": "array", "items": {"type": "object"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": ["string", "number"]},
    },
}


class StructuredResultParser:
    def __init__(self, repairer: StructuredOutputRepairer | None = None) -> None:
        self.repairer = repairer

    async def parse(
        self,
        *,
        raw_result: Any,
        context: DeepAgentInvocationContext,
    ) -> AgentTaskResult:
        candidate = _candidate(raw_result)
        try:
            return _parse(candidate)
        except (TypeError, ValueError, KeyError) as exc:
            if self.repairer is None:
                raise DeepAgentStructuredOutputError("structured task result invalid") from exc
            repaired = await self.repairer.repair(
                context=context,
                invalid_value=candidate,
                error_code="AGENT_TASK_RESULT_INVALID",
            )
            try:
                return _parse(repaired)
            except (TypeError, ValueError, KeyError) as repair_exc:
                raise DeepAgentStructuredOutputError(
                    "structured task result remained invalid after one repair"
                ) from repair_exc


def _candidate(raw_result: Any) -> Any:
    if isinstance(raw_result, dict) and "structured_response" in raw_result:
        return raw_result["structured_response"]
    if isinstance(raw_result, dict):
        messages = raw_result.get("messages")
        if isinstance(messages, list) and messages:
            content = getattr(messages[-1], "content", None)
            if content is None and isinstance(messages[-1], dict):
                content = messages[-1].get("content")
            return _decode(content)
    return _decode(raw_result)


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])
                if text.lstrip().startswith("json"):
                    text = text.lstrip()[4:].lstrip()
        return json.loads(text)
    return value


def _parse(value: Any) -> AgentTaskResult:
    if not isinstance(value, dict):
        raise TypeError("result must be object")
    expected = set(AGENT_TASK_RESULT_SCHEMA["required"])
    if set(value) != expected:
        raise ValueError("result fields do not match contract")
    return AgentTaskResult(
        status=AgentTaskStatus(str(value["status"])),
        summary=str(value["summary"]),
        decisions=tuple(str(item) for item in _list(value["decisions"])),
        artifact_refs=tuple(str(item) for item in _list(value["artifact_refs"])),
        knowledge_refs=tuple(str(item) for item in _list(value["knowledge_refs"])),
        proposed_operations=tuple(_dict(item) for item in _list(value["proposed_operations"])),
        open_questions=tuple(str(item) for item in _list(value["open_questions"])),
        confidence=str(value["confidence"]),
    )


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError("result collection must be array")
    return value


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("proposed operation must be object")
    return value
