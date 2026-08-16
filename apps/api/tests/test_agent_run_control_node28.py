from lumi_api.api.v1.app import create_contract_app


def test_agent_run_control_surface_is_command_only() -> None:
    schema = create_contract_app().openapi()
    paths = schema["paths"]
    resume = paths["/api/v1/agent-runs/{agent_run_id}/resume"]
    cancel = paths["/api/v1/agent-runs/{agent_run_id}/cancel"]
    assert set(resume) == {"post"}
    assert set(cancel) == {"post"}
    assert not any("checkpoint" in path for path in paths)
    assert not any("/state" in path for path in paths)
