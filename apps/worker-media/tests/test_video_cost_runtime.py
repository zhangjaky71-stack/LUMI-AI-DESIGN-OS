from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

import lumi_worker_media.video_cost_runtime as cost_module
from lumi_worker_media.video_cost_runtime import ScopedPostgresVideoCostObserver


class _FakeConnection:
    def __init__(
        self,
        *,
        organization_id: UUID,
        duplicate_scope: bool = False,
        confidence: str = "exact",
    ) -> None:
        self.organization_id = organization_id
        self.duplicate_scope = duplicate_scope
        self.confidence = confidence
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def fetch(self, sql: str, *args: object) -> list[dict[str, object]]:
        self.calls.append((sql, args))
        if "FROM video_generation_jobs" in sql:
            rows = [{"organization_id": self.organization_id}]
            if self.duplicate_scope:
                rows.append({"organization_id": uuid4()})
            return rows
        assert "FROM cost_ledger cl" in sql
        return [
            {
                "amount": Decimal("1.25000000"),
                "confidence": self.confidence,
                "pricing_snapshot_id": "price-v1",
                "external_provider_request_id": "video_provider_123",
            }
        ]

    async def close(self) -> None:
        self.closed = True


def _observer() -> ScopedPostgresVideoCostObserver:
    return ScopedPostgresVideoCostObserver("postgresql://runtime")


def test_video_cost_reconciliation_is_tenant_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    connection = _FakeConnection(organization_id=organization_id)

    async def connect(_dsn: str) -> _FakeConnection:
        return connection

    monkeypatch.setattr(cost_module.asyncpg, "connect", connect)
    paid_operation_id = uuid4()
    inserted = asyncio.run(
        _observer().record_terminal(
            video_job_id="video-job:abc",
            shot_id="hero",
            paid_operation_id=str(paid_operation_id),
            provider="openai",
            model="sora-2",
            provider_request_id="video_provider_123",
            amount_usd=Decimal("1.25000000"),
            confidence="EXACT",
            pricing_snapshot_id="price-v1",
        )
    )

    assert inserted is True
    assert connection.closed is True
    assert len(connection.calls) == 2
    scope_sql, scope_args = connection.calls[0]
    assert "job_snapshot ->> 'video_job_id' = $1" in scope_sql
    assert scope_args == ("video-job:abc",)
    ledger_sql, ledger_args = connection.calls[1]
    assert "io.organization_id = cl.organization_id" in ledger_sql
    assert "cl.organization_id = $1" in ledger_sql
    assert "io.organization_id = $1" in ledger_sql
    assert ledger_args == (organization_id, paid_operation_id, "openai", "sora-2")


def test_video_cost_duplicate_job_scope_fails_before_ledger_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(
        organization_id=uuid4(),
        duplicate_scope=True,
    )

    async def connect(_dsn: str) -> _FakeConnection:
        return connection

    monkeypatch.setattr(cost_module.asyncpg, "connect", connect)
    with pytest.raises(RuntimeError, match="VIDEO_COST_JOB_SCOPE_NOT_UNIQUE"):
        asyncio.run(
            _observer().record_terminal(
                video_job_id="video-job:duplicate",
                shot_id="hero",
                paid_operation_id=str(uuid4()),
                provider="openai",
                model="sora-2",
                provider_request_id="video_provider_123",
                amount_usd=Decimal("1.25000000"),
                confidence="EXACT",
                pricing_snapshot_id="price-v1",
            )
        )
    assert len(connection.calls) == 1
    assert connection.closed is True


def test_video_cost_confidence_uses_canonical_lowercase_ledger_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(organization_id=uuid4(), confidence="estimated")

    async def connect(_dsn: str) -> _FakeConnection:
        return connection

    monkeypatch.setattr(cost_module.asyncpg, "connect", connect)
    assert asyncio.run(
        _observer().record_terminal(
            video_job_id="video-job:estimated",
            shot_id="hero",
            paid_operation_id=str(uuid4()),
            provider="openai",
            model="sora-2",
            provider_request_id="video_provider_123",
            amount_usd=Decimal("1.25000000"),
            confidence="ESTIMATED",
            pricing_snapshot_id="price-v1",
        )
    ) is True
