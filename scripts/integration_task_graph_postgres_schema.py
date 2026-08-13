from __future__ import annotations

import asyncio
import os

import asyncpg


REQUIRED_TASK_COLUMNS = {
    "task_graph_id",
    "recipe_step_id",
    "task_key",
    "state_version",
    "lease_owner",
    "lease_expires_at",
    "heartbeat_at",
    "retry_not_before",
    "wait_reason",
    "external_ref",
    "progress_current",
    "progress_total",
    "dynamic_depth",
    "dynamic_child_limit",
    "concurrency_group",
    "concurrency_limit",
}


async def main_async() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    connection = await asyncpg.connect(database_url)
    try:
        tables = {
            row["table_name"]
            for row in await connection.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'task_graph_instances',
                    'task_attempts'
                  )
                """
            )
        }
        assert tables == {"task_graph_instances", "task_attempts"}
        task_columns = {
            row["column_name"]
            for row in await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'tasks'
                """
            )
        }
        assert REQUIRED_TASK_COLUMNS <= task_columns
        graph_columns = {
            row["column_name"]
            for row in await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'task_graph_instances'
                """
            )
        }
        assert {
            "recipe_definition_hash",
            "recipe_provenance_hash",
            "task_graph_template_hash",
            "provenance_hash",
            "task_count",
            "completed_count",
            "state_version",
        } <= graph_columns
        attempt_columns = {
            row["column_name"]
            for row in await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'task_attempts'
                """
            )
        }
        assert {
            "task_graph_id",
            "task_id",
            "attempt_number",
            "logical_operation_key",
            "status",
            "cost_amount_usd",
        } <= attempt_columns
        indexes = {
            row["indexname"]
            for row in await connection.fetch(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'tasks',
                    'task_graph_instances',
                    'task_attempts'
                  )
                """
            )
        }
        assert {
            "uq_tasks_graph_task_key",
            "ix_tasks_ready_claim",
            "ix_tasks_lease_reap",
            "ix_tasks_concurrency_group",
            "ix_task_graph_instances_org_status",
            "ix_task_attempts_graph_created",
            "ix_task_attempts_logical_operation",
        } <= indexes
        uniqueness = {
            row["constraint_name"]
            for row in await connection.fetch(
                """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'task_attempts'
                  AND constraint_type = 'UNIQUE'
                """
            )
        }
        assert "uq_task_attempts_task_number" in uniqueness
        assert not any("logical_operation" in item for item in uniqueness)
        grants = await connection.fetch(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'lumi_app'
              AND table_name IN (
                'task_graph_instances',
                'task_attempts'
              )
            """
        )
        privilege_set = {
            (row["table_name"], row["privilege_type"])
            for row in grants
        }
        for table in ("task_graph_instances", "task_attempts"):
            assert (table, "SELECT") in privilege_set
            assert (table, "INSERT") in privilege_set
            assert (table, "UPDATE") in privilege_set
            assert (table, "DELETE") not in privilege_set
    finally:
        await connection.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-33 Task Graph PostgreSQL schema acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
