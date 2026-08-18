from __future__ import annotations

import inspect
from datetime import timedelta
from uuid import uuid4

import pytest

from lumi_api.api.v1 import collaboration_routes
from lumi_api.collaboration.contracts import PresenceState
from lumi_api.collaboration.postgres_repository import PostgresCollaborationRepository as BaseRepository
from lumi_api.collaboration.presence import (
    PRESENCE_HEARTBEAT_SECONDS,
    PRESENCE_TTL_SECONDS,
    InMemoryPresencePort,
)
from lumi_api.persistence.models_collaboration import (
    CommentModel,
    CommentRevisionModel,
    CommentThreadModel,
)


def test_presence_is_ttl_only_and_expires() -> None:
    assert PRESENCE_TTL_SECONDS == 30
    assert PRESENCE_HEARTBEAT_SECONDS == 10
    port = InMemoryPresencePort()
    project_id = uuid4()
    value = PresenceState(
        user_id=str(uuid4()),
        display_name="A",
        color="#112233",
        project_id=project_id,
        last_seen_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    stored = port.heartbeat(value)
    assert port.list_project(project_id, now=stored.last_seen_at)
    assert port.list_project(
        project_id,
        now=stored.last_seen_at + timedelta(seconds=PRESENCE_TTL_SECONDS + 1),
    ) == ()


def test_presence_has_no_durable_sqlalchemy_model() -> None:
    model_names = {CommentThreadModel.__tablename__, CommentModel.__tablename__, CommentRevisionModel.__tablename__}
    assert model_names == {"comment_threads", "comments", "comment_revisions"}
    assert all("presence" not in name for name in model_names)


def test_comment_delete_projection_hides_body_but_audit_can_preserve_snapshot() -> None:
    organization_id = uuid4()
    comment_id = uuid4()
    thread_id = uuid4()
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    projected = BaseRepository._comment(
        {
            "id": comment_id,
            "organization_id": organization_id,
            "thread_id": thread_id,
            "body": "sensitive original comment",
            "mentions_json": [],
            "created_by": str(uuid4()),
            "revision": 2,
            "created_at": now,
            "edited_at": None,
            "deleted_at": now,
        }
    )
    assert projected.body == "[deleted]"
    assert projected.deleted_at == now


def test_collaboration_routes_do_not_create_design_mutation_bypass() -> None:
    source = inspect.getsource(collaboration_routes)
    forbidden = (
        "CanvasCommandBatchRequest",
        "apply_commands(",
        "DesignOperation",
        "design_document_service",
        "UPDATE design_",
        "INSERT INTO design_",
    )
    for marker in forbidden:
        assert marker not in source


def test_comment_mutations_are_if_match_fenced() -> None:
    edit_source = inspect.getsource(collaboration_routes.edit_comment)
    delete_source = inspect.getsource(collaboration_routes.delete_comment)
    assert "if_match: IfMatch" in edit_source
    assert "expected_revision=_expected_revision(if_match)" in edit_source
    assert "if_match: IfMatch" in delete_source
    assert "expected_revision=_expected_revision(if_match)" in delete_source


def test_thread_creation_binds_exact_artifact_version() -> None:
    source = inspect.getsource(collaboration_routes.create_comment_thread)
    assert "artifact_version_id=body.artifact_version_id" in source
    assert "artifact_id=artifact_id" in source
    assert "project_id=project_id" in source


def test_presence_actor_identity_is_server_authoritative() -> None:
    source = inspect.getsource(collaboration_routes.heartbeat_presence)
    assert "actor_id=_actor_id(request)" in source
    assert "user_id" not in collaboration_routes.PresenceHeartbeatRequest.model_fields


def test_comment_schema_has_revision_audit_table() -> None:
    assert "revision" in CommentModel.__table__.c
    assert "edited_at" in CommentModel.__table__.c
    assert "deleted_at" in CommentModel.__table__.c
    assert "revision_number" in CommentRevisionModel.__table__.c
    assert "body_snapshot" in CommentRevisionModel.__table__.c
    assert "artifact_version_id" in CommentThreadModel.__table__.c


def test_presence_ttl_rejects_pathological_values() -> None:
    port = InMemoryPresencePort()
    value = PresenceState(
        user_id=str(uuid4()),
        display_name="A",
        color="#112233",
        project_id=uuid4(),
        last_seen_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    with pytest.raises(ValueError, match="PRESENCE_TTL_OUT_OF_RANGE"):
        port.heartbeat(value, ttl_seconds=0)
