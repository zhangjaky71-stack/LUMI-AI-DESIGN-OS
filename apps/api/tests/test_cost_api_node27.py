from __future__ import annotations

from lumi_api.api.v1.app import create_contract_app


def test_cost_api_is_read_only_and_mounted() -> None:
    document = create_contract_app().openapi()
    paths = document["paths"]
    summary = paths["/api/v1/costs/summary"]
    usage = paths["/api/v1/costs/usage"]
    assert set(summary) == {"get"}
    assert set(usage) == {"get"}


def test_cost_api_does_not_expose_financial_write_routes() -> None:
    document = create_contract_app().openapi()
    mutating = {"post", "put", "patch", "delete"}
    for path, methods in document["paths"].items():
        if not path.startswith("/api/v1/costs"):
            continue
        assert mutating.isdisjoint(methods)
