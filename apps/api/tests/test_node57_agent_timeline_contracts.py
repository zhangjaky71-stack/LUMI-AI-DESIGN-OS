from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_api.api.v1.agent_workspace_schemas import AgentRunSafeEventResponse

RUN_ID = UUID("0198a100-0000-7000-8000-000000000001")
PROJECT_ID = UUID("0198a100-0000-7000-8000-000000000002")


def event(payload: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": "evt-57",
        "event_type": "tool.call",
        "agent_run_id": RUN_ID,
        "project_id": PROJECT_ID,
        "occurred_at": datetime(2026, 8, 18, tzinfo=UTC),
        "payload": payload,
    }


@pytest.mark.parametrize(
    "private_payload",
    [
        {"reasoning": "private"},
        {"nested": {"provider_api_key": "secret"}},
        {"nested": [{"access_token": "secret"}]},
        {"authorization": "Bearer secret"},
        {"headers": {"X-Key": "secret"}},
        {"credentials": {"username": "u", "password": "p"}},
    ],
)
def test_safe_event_rejects_reasoning_and_secret_like_fields(
    private_payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="AGENT_WORKSPACE_PRIVATE_EVENT_FIELD_FORBIDDEN"):
        AgentRunSafeEventResponse.model_validate(event(private_payload))


def test_safe_event_allows_public_observability_fields() -> None:
    parsed = AgentRunSafeEventResponse.model_validate(
        event(
            {
                "tool_name": "web_search",
                "safe_summary": "Searched public sources",
                "task_id": "task-1",
                "trace_id": "trace-public-reference",
                "token_count": 321,
                "retry_attempt": 2,
                "fallback_provider": "provider-b",
            }
        )
    )
    assert parsed.payload["safe_summary"] == "Searched public sources"
    assert parsed.payload["token_count"] == 321
