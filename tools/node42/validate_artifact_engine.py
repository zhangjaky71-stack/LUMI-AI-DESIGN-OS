from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    required = [
        "apps/api/src/lumi_api/artifact_engine/contracts.py",
        "apps/api/src/lumi_api/artifact_engine/ports.py",
        "apps/api/src/lumi_api/artifact_engine/repository.py",
        "apps/api/src/lumi_api/artifact_engine/postgres_repository.py",
        "apps/api/src/lumi_api/artifact_engine/service.py",
        "apps/api/src/lumi_api/persistence/models_artifacts.py",
        "apps/api/src/lumi_api/artifact_engine/compare.py",
        "apps/api/src/lumi_api/api/v1/artifact_engine_routes.py",
        "apps/api/migrations/versions/20260817_0011_artifact_engine_runtime.py",
        "apps/api/migrations/versions/20260817_0011_sql/up_01.sql",
        "apps/api/migrations/versions/20260817_0011_sql/up_02.sql",
        "apps/api/tests/test_artifact_engine_node42.py",
    ]
    for item in required:
        assert (ROOT / item).is_file(), item

    migration = read("apps/api/migrations/versions/20260817_0011_artifact_engine_runtime.py")
    assert 'revision = "20260817_0011"' in migration
    assert 'down_revision = "20260816_0010"' in migration

    up = read("apps/api/migrations/versions/20260817_0011_sql/up_01.sql") + read(
        "apps/api/migrations/versions/20260817_0011_sql/up_02.sql"
    )
    for marker in (
        "base_version_id",
        "parent_version_id",
        "primary_file_id",
        "design_document_version_id",
        "constraint_snapshot_hash",
        "rights_json",
        "REFERENCE_USED",
        "artifact_version_approvals",
        "artifact_gc_marks",
        "artifact_gc_audits",
        "artifact_outbox_events",
        "uq_artifact_files_version_bucket_key",
    ):
        assert marker in up, marker
    assert "DROP CONSTRAINT uq_artifact_files_bucket_key" in up
    assert "ALTER COLUMN created_by_id TYPE VARCHAR(200)" in up
    assert "WHERE state = 'MARKED'" in up

    postgres = read("apps/api/src/lumi_api/artifact_engine/postgres_repository.py")
    for marker in (
        "FOR UPDATE",
        "expected_head_version_id",
        "organization_id=:organization_id",
        "artifact_outbox_events",
        "create_artifact_bundle_with_initial_version",
    ):
        assert marker in postgres, marker

    orm = read("apps/api/src/lumi_api/persistence/models_artifacts.py")
    assert "uq_artifact_files_version_bucket_key" in orm
    assert "GENERATED_FROM" in orm and "REFERENCE_USED" in orm
    assert "ArtifactOutboxEventModel" in orm

    routes = read("apps/api/src/lumi_api/api/v1/artifact_engine_routes.py")
    for endpoint in (
        '"/artifacts/{artifact_id}"',
        '"/artifacts/{artifact_id}/versions"',
        '"/artifact-versions/{version_id}"',
        '"/artifact-versions/{version_id}/lineage"',
        '"/artifact-versions/{version_id}/fork"',
        '"/artifact-versions/{version_id}/restore"',
        '"/artifact-versions/{version_id}/approve"',
        '"/artifact-versions/{left_id}/compare/{right_id}"',
    ):
        assert endpoint in routes, endpoint

    gap = json.loads(read("reports/nodes/NODE-42/gap-ledger.json"))
    assert gap["node"] == "NODE-42"
    assert len(gap["gaps"]) == 5
    assert len({item["id"] for item in gap["gaps"]}) == 5

    forbidden = ("OpenAI", "Anthropic", "langchain", "langgraph")
    core = "\n".join(
        read(path)
        for path in (
            "apps/api/src/lumi_api/artifact_engine/repository.py",
            "apps/api/src/lumi_api/artifact_engine/postgres_repository.py",
            "apps/api/src/lumi_api/artifact_engine/service.py",
        "apps/api/src/lumi_api/persistence/models_artifacts.py",
        )
    )
    assert not any(token in core for token in forbidden)

    print("NODE42_ARTIFACT_ENGINE_VALIDATION_PASS")
    print("required_endpoints=8")
    print("production_gaps=5")


if __name__ == "__main__":
    main()
