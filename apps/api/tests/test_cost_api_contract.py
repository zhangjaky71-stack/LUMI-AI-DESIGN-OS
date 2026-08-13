from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from lumi_api.api import create_contract_app
from lumi_api.api.v1.context import RequestContext
from lumi_api.api.v1.contracts import CostSummaryResource, UsageSummaryResource


class FakeCostGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, UUID | None]] = []

    async def get_cost_summary(
        self,
        context: RequestContext,
        *,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
    ) -> CostSummaryResource:
        self.calls.append(("cost", context.organization_id, project_id))
        return CostSummaryResource(
            organization_id=context.organization_id,
            project_id=project_id,
            currency="USD",
            actual_cost=Decimal("1.25"),
            adjustments=Decimal("0.10"),
            reversals=Decimal("-0.25"),
            net_provider_cost=Decimal("1.10"),
            active_reservations=Decimal("0.30"),
            unknown_cost_entries=1,
            from_time=from_time,
            to_time=to_time,
        )

    async def list_usage_summary(
        self,
        context: RequestContext,
        *,
        from_time: datetime,
        to_time: datetime,
        project_id: UUID | None = None,
    ) -> list[UsageSummaryResource]:
        self.calls.append(("usage", context.organization_id, project_id))
        return [
            UsageSummaryResource(
                organization_id=context.organization_id,
                project_id=project_id,
                metric="input_tokens",
                quantity=Decimal("1200"),
                unit="tokens",
                from_time=from_time,
                to_time=to_time,
            )
        ]


class CostApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = FakeCostGateway()
        self.client = TestClient(create_contract_app(gateway=self.gateway))  # type: ignore[arg-type]
        self.organization_id = uuid4()
        self.project_id = uuid4()
        self.headers = {"X-Lumi-Organization-Id": str(self.organization_id)}
        self.params = {
            "from_time": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
            "to_time": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
        }

    def test_openapi_exposes_cost_and_usage_routes(self) -> None:
        paths = self.client.get("/api/openapi.json").json()["paths"]
        self.assertIn("/api/v1/usage", paths)
        self.assertIn("/api/v1/costs/summary", paths)
        self.assertIn("/api/v1/projects/{project_id}/costs", paths)

    def test_organization_cost_summary_is_aggregated(self) -> None:
        response = self.client.get(
            "/api/v1/costs/summary",
            headers=self.headers,
            params=self.params,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["organization_id"], str(self.organization_id))
        self.assertEqual(Decimal(body["net_provider_cost"]), Decimal("1.10"))
        self.assertNotIn("provider", body)
        self.assertNotIn("provider_request_id", body)

    def test_project_cost_summary_preserves_tenant_scope(self) -> None:
        response = self.client.get(
            f"/api/v1/projects/{self.project_id}/costs",
            headers=self.headers,
            params=self.params,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["project_id"], str(self.project_id))
        self.assertIn(("cost", self.organization_id, self.project_id), self.gateway.calls)

    def test_usage_summary_is_aggregated(self) -> None:
        params = {**self.params, "project_id": str(self.project_id)}
        response = self.client.get(
            "/api/v1/usage",
            headers=self.headers,
            params=params,
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["data"][0]
        self.assertEqual(item["metric"], "input_tokens")
        self.assertEqual(Decimal(item["quantity"]), Decimal("1200"))
        self.assertIn(("usage", self.organization_id, self.project_id), self.gateway.calls)

    def test_invalid_range_fails_before_gateway(self) -> None:
        response = self.client.get(
            "/api/v1/costs/summary",
            headers=self.headers,
            params={
                "from_time": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
                "to_time": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "COST_TIME_RANGE_INVALID")
        self.assertEqual(self.gateway.calls, [])


if __name__ == "__main__":
    unittest.main()
