from lumi_agent_runtime.smoke import REQUIRED_MODULES, check_imports


def test_required_modules_are_declared() -> None:
    assert REQUIRED_MODULES == ("langgraph", "langchain", "deepagents")


def test_agent_dependencies_import() -> None:
    versions = check_imports()
    assert set(versions) == set(REQUIRED_MODULES)
