# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import ast
from pathlib import Path

import asyncpg

import test_database_integration as suite

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "apps" / "api" / "migrations" / "versions"


def discover_head_revision() -> str:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values: dict[str, str | None] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id not in {
                "revision",
                "down_revision",
            }:
                continue
            if isinstance(node.value, ast.Constant) and (
                isinstance(node.value.value, str) or node.value.value is None
            ):
                values[target.id] = node.value.value
        revision = values.get("revision")
        if revision:
            revisions.add(revision)
        parent = values.get("down_revision")
        if parent:
            parents.add(parent)
    heads = revisions - parents
    if len(heads) != 1:
        raise AssertionError(f"expected exactly one Alembic head, got {sorted(heads)}")
    return next(iter(heads))


async def assert_current_revision() -> None:
    connection = await asyncpg.connect(suite.MIGRATION_DSN)
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        expected = discover_head_revision()
        assert revision == expected, (revision, expected)
    finally:
        await connection.close()


async def main() -> None:
    tests = (
        assert_current_revision,
        suite.test_rls_isolation,
        suite.test_cross_tenant_reference_guard,
        suite.test_optimistic_concurrency,
        suite.test_exact_money_and_idempotency,
        suite.test_task_dag_cycle_guard,
        suite.test_artifact_lineage_cycle_guard,
        suite.test_approved_version_and_ledger_immutability,
        suite.test_outbox_atomic_rollback,
    )
    for test in tests:
        await test()
        print(f"PASS {test.__name__}")
    print(f"PostgreSQL integration PASS: {len(tests)} invariant groups; head is current")


if __name__ == "__main__":
    asyncio.run(main())
