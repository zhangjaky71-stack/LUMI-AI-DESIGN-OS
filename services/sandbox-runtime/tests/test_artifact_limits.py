from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_sandbox_runtime.docker_backend import _base64_transport_budget
from lumi_sandbox_runtime.models import SandboxSpec

ORG = UUID("01910000-0000-7000-8000-000000000001")
RUN = UUID("01910000-0000-7000-8000-000000000301")


def test_artifact_limit_cannot_exceed_disk_budget() -> None:
    with pytest.raises(ValidationError, match="max_artifact_bytes"):
        SandboxSpec(
            organization_id=ORG,
            agent_run_id=RUN,
            image="lumi-sandbox:node21",
            image_version="node21-v1",
            disk_limit_mb=64,
            max_artifact_bytes=65 * 1024 * 1024,
        )


def test_base64_transport_budget_retains_full_encoded_artifact() -> None:
    raw_bytes = 16 * 1024 * 1024
    encoded_bytes = ((raw_bytes + 2) // 3) * 4
    total_transport = _base64_transport_budget(raw_bytes)
    assert total_transport // 2 > encoded_bytes
