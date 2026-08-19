from __future__ import annotations

import asyncio
import json
import unittest
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.estimate_transport import (
    HttpModelGatewayEstimateClient,
    decode_route_estimate,
    encode_route_candidate,
)
from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelRequest,
    RouteCandidate,
)

_SECRET = "s" * 48


class _RecordingEstimateClient(HttpModelGatewayEstimateClient):
    def __init__(self) -> None:
        super().__init__(
            base_url="http://model-gateway.internal:8080",
            auth_secret=_SECRET,
            caller_service="worker-media",
        )
        self.paths: list[str] = []
        self.bodies: list[bytes] = []
        self.headers: list[dict[str, str]] = []

    def _request(
        self,
        path: str,
        body: bytes,
        auth_headers: dict[str, str],
    ) -> dict[str, object]:
        self.paths.append(path)
        self.bodies.append(body)
        self.headers.append(auth_headers)
        return {
            "provider": "openai",
            "model": "gpt-image-1.5",
            "estimate": {
                "amount_usd": "0.125",
                "confidence": "estimated",
                "price_snapshot_id": "image-price-2026-08",
            },
            "reason_codes": ["PROFILE_MATCH", "CAPABILITY_MATCH"],
        }


class EstimateTransportTests(unittest.TestCase):
    def test_route_candidate_codec_preserves_decimal_cost(self) -> None:
        candidate = RouteCandidate(
            provider="openai",
            model="gpt-image-1.5",
            estimate=CostEstimate(
                amount_usd=Decimal("0.125"),
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id="snapshot-1",
            ),
            score=91,
            reason_codes=("PROFILE_MATCH",),
        )
        payload = encode_route_candidate(candidate)
        decoded = decode_route_estimate(payload)
        self.assertEqual(decoded.amount_usd, Decimal("0.125"))
        self.assertEqual(decoded.provider, "openai")
        self.assertEqual(decoded.model, "gpt-image-1.5")
        self.assertEqual(decoded.reason_codes, ("PROFILE_MATCH",))

    def test_estimate_uses_distinct_signed_internal_path(self) -> None:
        client = _RecordingEstimateClient()
        request = ModelRequest(
            organization_id=UUID("11111111-1111-1111-1111-111111111111"),
            operation_id=UUID("22222222-2222-2222-2222-222222222222"),
            capability=Capability.IMAGE_GENERATE,
            inputs={"width": 1024, "height": 1024},
            budget_limit_usd=Decimal("1.00"),
        )
        estimate = asyncio.run(client.estimate(request))
        self.assertEqual(client.paths, ["/internal/v1/models/estimate"])
        payload = json.loads(client.bodies[0].decode("utf-8"))
        self.assertEqual(payload["capability"], "image.generate")
        self.assertEqual(client.headers[0]["X-Lumi-Service"], "worker-media")
        self.assertEqual(len(client.headers[0]["X-Lumi-Signature"]), 64)
        self.assertEqual(estimate.amount_usd, Decimal("0.125"))

    def test_invalid_estimate_amount_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "MODEL_GATEWAY_ESTIMATE_AMOUNT_INVALID"):
            decode_route_estimate(
                {
                    "provider": "openai",
                    "model": "gpt-image-1.5",
                    "estimate": {
                        "amount_usd": "-1",
                        "confidence": "estimated",
                        "price_snapshot_id": "snapshot",
                    },
                    "reason_codes": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
