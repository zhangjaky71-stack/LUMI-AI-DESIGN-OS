from __future__ import annotations

import os
import unittest
from typing import cast
from unittest.mock import patch

from lumi_model_gateway import (
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelGateway,
    ModelRouter,
)
from lumi_model_gateway.budget import RequestBudgetGuard
from lumi_model_gateway.errors import DurableBudgetGuardRequiredError
from lumi_model_gateway.ports import BudgetGuard
from lumi_model_gateway.testing import RecordingPaidInvocationGuard


def _gateway(*, budget_guard: BudgetGuard | None = None) -> ModelGateway:
    registry = InMemoryProviderRegistry((MockProvider(),))
    health = InMemoryProviderHealthRegistry()
    router = ModelRouter(registry=registry, health=health)
    return ModelGateway(
        registry=registry,
        health=health,
        router=router,
        paid_guard=RecordingPaidInvocationGuard(),
        budget_guard=budget_guard,
    )


class ProductionBudgetGuardTests(unittest.TestCase):
    def test_production_rejects_implicit_request_local_budget_guard(self) -> None:
        with patch.dict(os.environ, {"LUMI_ENV": "production"}, clear=False):
            with self.assertRaises(DurableBudgetGuardRequiredError):
                _gateway()

    def test_staging_rejects_explicit_request_local_budget_guard(self) -> None:
        with patch.dict(os.environ, {"LUMI_ENV": "staging"}, clear=False):
            with self.assertRaises(DurableBudgetGuardRequiredError):
                _gateway(budget_guard=RequestBudgetGuard())

    def test_production_accepts_explicit_non_local_budget_guard(self) -> None:
        durable_guard = cast(BudgetGuard, object())
        with patch.dict(os.environ, {"LUMI_ENV": "production"}, clear=False):
            gateway = _gateway(budget_guard=durable_guard)
        self.assertIs(gateway.budget_guard, durable_guard)

    def test_development_keeps_request_local_fallback(self) -> None:
        with patch.dict(os.environ, {"LUMI_ENV": "development"}, clear=False):
            gateway = _gateway()
        self.assertIsInstance(gateway.budget_guard, RequestBudgetGuard)
