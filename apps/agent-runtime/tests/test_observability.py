from __future__ import annotations

import pytest

from lumi_agent_runtime.observability import (
    AgentTraceRefs,
    LangSmithPolicy,
    best_effort_observed_call,
    best_effort_trace,
    langsmith_environment,
)


def test_langsmith_defaults_to_no_content_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LANGSMITH_TRACING",
        "LANGSMITH_PROJECT",
        "LANGSMITH_TRACING_MODE",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        monkeypatch.delenv(name, raising=False)

    policy = LangSmithPolicy.from_environment()
    assert policy.enabled is False
    assert policy.tracing_mode == "otel"
    assert policy.hide_inputs is True
    assert policy.hide_outputs is True


def test_production_policy_rejects_full_prompt_capture() -> None:
    policy = LangSmithPolicy(
        enabled=True,
        project="lumi-production",
        tracing_mode="hybrid",
        hide_inputs=False,
        hide_outputs=True,
        hide_metadata=False,
    )
    with pytest.raises(ValueError, match="LANGSMITH_PRODUCTION_CONTENT_CAPTURE_FORBIDDEN"):
        policy.validate_production_privacy()


def test_langsmith_environment_never_contains_api_key() -> None:
    policy = LangSmithPolicy(
        enabled=True,
        project="lumi-staging",
        tracing_mode="hybrid",
        hide_inputs=True,
        hide_outputs=True,
        hide_metadata=False,
    )
    environment = langsmith_environment(policy)
    assert environment["LANGSMITH_TRACING"] == "true"
    assert environment["LANGSMITH_HIDE_INPUTS"] == "true"
    assert "LANGSMITH_API_KEY" not in environment
    assert "LANGSMITH_ENDPOINT" not in environment


def test_trace_metadata_contains_refs_not_user_content() -> None:
    refs = AgentTraceRefs(
        environment="test",
        agent_run_id="run-1",
        organization_id="org-1",
        project_id="project-1",
        task_id="task-1",
        operation_id="op-1",
        trace_id="a" * 32,
    )
    metadata = refs.safe_metadata()
    assert metadata["agent_run_id"] == "run-1"
    assert set(metadata) == {
        "environment",
        "agent_run_id",
        "organization_id",
        "project_id",
        "task_id",
        "operation_id",
        "trace_id",
    }


def test_langsmith_outage_never_fails_business_operation() -> None:
    def outage() -> None:
        raise RuntimeError("langsmith unavailable")

    assert best_effort_trace(outage) is False
    result = best_effort_observed_call(lambda: "business-result", before=outage, after=outage)
    assert result == "business-result"


def test_business_failure_is_not_swallowed_by_observability_wrapper() -> None:
    def business_failure() -> str:
        raise RuntimeError("business failed")

    with pytest.raises(RuntimeError, match="business failed"):
        best_effort_observed_call(business_failure, before=lambda: None, after=lambda: None)
