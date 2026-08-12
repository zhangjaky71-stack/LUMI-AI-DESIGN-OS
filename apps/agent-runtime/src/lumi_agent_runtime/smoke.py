import importlib
import json

REQUIRED_MODULES = ("langgraph", "langchain", "deepagents")


def check_imports() -> dict[str, str]:
    versions: dict[str, str] = {}
    for module_name in REQUIRED_MODULES:
        module = importlib.import_module(module_name)
        versions[module_name] = str(getattr(module, "__version__", "import-ok"))
    return versions


def main() -> None:
    print(json.dumps({"service": "agent-runtime", "status": "ok", "imports": check_imports()}))
