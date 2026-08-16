from __future__ import annotations

import ast
from pathlib import Path

from lumi_worker_media.queue_contracts import JobKind, queue_for
from lumi_worker_media.topology import DEAD_LETTER_EXCHANGE, DOMAIN_EXCHANGE, JOBS_EXCHANGE

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "apps" / "worker-media" / "src" / "lumi_worker_media"
API = ROOT / "apps" / "api" / "src" / "lumi_api"
MIGRATION = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0005_queue_event_runtime.py"
SQL_DIR = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0005_sql"


def assert_topology() -> None:
    assert JOBS_EXCHANGE.name == "lumi.jobs" and JOBS_EXCHANGE.type == "direct"
    assert DOMAIN_EXCHANGE.name == "lumi.domain" and DOMAIN_EXCHANGE.type == "topic"
    assert DEAD_LETTER_EXCHANGE.name == "lumi.dlx" and DEAD_LETTER_EXCHANGE.type == "topic"
    assert queue_for(JobKind.IMAGE_TRANSFORM) == "lumi.media.image"
    assert queue_for(JobKind.VIDEO_RENDER) == "lumi.media.video"
    assert queue_for(JobKind.EXPORT_PACKAGE) == "lumi.media.export"
    assert queue_for(JobKind.ASSET_VALIDATE) == "lumi.asset.processing"


def assert_worker_reliability_flags() -> None:
    app = (WORKER / "app.py").read_text(encoding="utf-8")
    assert "task_acks_late=False" in app
    assert "task_reject_on_worker_lost=False" in app
    assert "worker_prefetch_multiplier=1" in app
    assert 'task_serializer="json"' in app
    assert "pickle" not in app.casefold()
    events = (WORKER / "event_runtime.py").read_text(encoding="utf-8")
    assert '"lumi.events/1.0"' in events
    assert "FOR UPDATE SKIP LOCKED" in (
        WORKER / "postgres_runtime.py"
    ).read_text(encoding="utf-8")
    assert "SafeKombuEventConsumer" in (
        WORKER / "consumer.py"
    ).read_text(encoding="utf-8")


def assert_migration() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260816_0005"' in source
    assert 'down_revision = "20260816_0004"' in source
    sql = "\n".join(path.read_text(encoding="utf-8") for path in sorted(SQL_DIR.glob("up_*.sql")))
    for fragment in (
        "runtime_jobs",
        "dead_letter_records",
        "next_publish_at",
        "tenant_isolation_runtime_jobs",
        "tenant_isolation_dead_letter_records",
        "lumi_queue_runtime_same_tenant_guard",
    ):
        assert fragment in sql, fragment


def assert_api_does_not_import_worker_package() -> None:
    for path in API.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("lumi_worker_media") for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("lumi_worker_media")
    bridge = (API / "events" / "runtime_bridge.py").read_text(encoding="utf-8")
    assert "lumi.project.created.v1" in bridge
    assert "lumi.asset.ready.v1" in bridge
    scheduler = (API / "queueing" / "contracts.py").read_text(encoding="utf-8")
    assert 'job_kind="asset.validate"' in scheduler


def main() -> None:
    assert_topology()
    assert_worker_reliability_flags()
    assert_migration()
    assert_api_does_not_import_worker_package()
    print(
        "NODE19_QUEUE_RUNTIME_VALIDATION_PASS: topology, JSON-only messages, canonical events, "
        "tenant-sharded outbox, inbox idempotency, DLQ, 0005 migration"
    )


if __name__ == "__main__":
    main()
