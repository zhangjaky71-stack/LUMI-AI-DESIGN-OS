from __future__ import annotations

import inspect
from pathlib import Path

from lumi_api.collaboration import factory as collaboration_factory
from lumi_api.collaboration import service as collaboration_service
from lumi_api.collaboration.postgres_repository import PostgresCollaborationRepository as TransactionalBase
from lumi_api.collaboration.repository import PostgresCollaborationRepository

ROOT = Path(__file__).resolve().parents[3]


def test_service_and_factory_use_hardened_repository_facade() -> None:
    service_source = inspect.getsource(collaboration_service)
    factory_source = inspect.getsource(collaboration_factory)
    assert "from .repository import PostgresCollaborationRepository" in service_source
    assert "from .repository import PostgresCollaborationRepository" in factory_source
    assert PostgresCollaborationRepository is not TransactionalBase
    assert issubclass(PostgresCollaborationRepository, TransactionalBase)


def test_project_access_is_explicit_membership_not_org_only() -> None:
    source = inspect.getsource(PostgresCollaborationRepository.get_access)
    assert "organization_members" in source
    assert "project_members" in source
    assert "p.created_by" in source
    assert "PROJECT_MEMBERSHIP_REQUIRED" in source
    assert "om.deleted_at" not in source


def test_mentions_require_project_access_and_notification_excludes_body() -> None:
    mention_validation = inspect.getsource(PostgresCollaborationRepository._validate_mentions)
    notification = inspect.getsource(TransactionalBase._emit_mentions)
    assert "project_members" in mention_validation
    assert "MENTIONED_USER_PROJECT_ACCESS_REQUIRED" in mention_validation
    assert '"project_id"' in notification
    assert '"thread_id"' in notification
    assert '"comment_id"' in notification
    assert '"mentioned_user_id"' in notification
    assert '"actor_id"' in notification
    assert '"body"' not in notification
    assert "comment body" not in notification.lower()


def test_thread_resolution_is_not_artifact_approval() -> None:
    source = inspect.getsource(PostgresCollaborationRepository.set_thread_status)
    assert "THREAD_OWNER_OR_EDITOR_REQUIRED" in source
    assert "comment_threads" in source
    for forbidden in (
        "artifact_versions",
        "approve_version",
        "ArtifactVersionStatus.APPROVED",
        "validation_ref",
    ):
        assert forbidden not in source


def test_collaboration_migration_is_linear_and_presence_is_ephemeral() -> None:
    migration = ROOT / "apps/api/migrations/versions/20260818_0021_collaboration.py"
    up = ROOT / "apps/api/migrations/versions/20260818_0021_sql/up.sql"
    down = ROOT / "apps/api/migrations/versions/20260818_0021_sql/down.sql"
    migration_text = migration.read_text(encoding="utf-8")
    up_text = up.read_text(encoding="utf-8")
    down_text = down.read_text(encoding="utf-8")

    assert 'revision = "20260818_0021"' in migration_text
    assert 'down_revision = "20260818_0020"' in migration_text
    assert "CREATE TABLE comment_threads" in up_text
    assert "artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id)" in up_text
    assert "CREATE TABLE comments" in up_text
    assert "CREATE TABLE comment_revisions" in up_text
    assert "UNIQUE (comment_id, revision_number)" in up_text
    assert "presence" not in up_text.lower()
    assert "DROP TABLE IF EXISTS comment_threads" in down_text


def test_collaboration_schema_never_declares_presence_table() -> None:
    models = (ROOT / "apps/api/src/lumi_api/persistence/models_collaboration.py").read_text(encoding="utf-8")
    assert '__tablename__ = "comment_threads"' in models
    assert '__tablename__ = "comments"' in models
    assert '__tablename__ = "comment_revisions"' in models
    assert '__tablename__ = "presence"' not in models
    assert '__tablename__ = "presences"' not in models
