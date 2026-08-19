from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.service import _build_hosted_adapters


class HostedAdapterCoverageTests(unittest.TestCase):
    def test_hosted_adapters_exactly_cover_enabled_p0_registry(self) -> None:
        environment = {
            "LUMI_TOOL_DATA_URL": "http://api.test.internal:8000",
            "LUMI_TOOL_DATA_AUTH_SECRET": "d" * 64,
            "LUMI_SANDBOX_RUNTIME_URL": "http://sandbox.test.internal:8080",
            "LUMI_SANDBOX_RUNTIME_AUTH_SECRET": "s" * 64,
            "LUMI_BRAVE_SEARCH_API_KEY": "provider-secret",
        }
        with patch.dict(os.environ, environment, clear=False):
            adapters = _build_hosted_adapters()

        required = {
            definition.key
            for definition in build_p0_registry().definitions()
            if definition.enabled
        }
        self.assertEqual(set(adapters), required)
        self.assertEqual(len(adapters), 8)


if __name__ == "__main__":
    unittest.main()
