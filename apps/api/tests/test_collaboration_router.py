from __future__ import annotations

from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient

from lumi_api.collaboration_router import (
    CollaborationWorkspaceMetadata,
    create_collaboration_router,
)
from lumi_project_core.collaboration import (
    CollaborationActor,
    CollaborationEngine,
    InMemoryCanonicalDesign,
    InMemoryCollaborationRepository,
    InMemoryPresenceStore,
    RecordingCollaborationAudit,
    RecordingCollaborationNotifications,
    RecordingConstraintValidator,
    StaticCollaborationAuthorization,
)

ORG = "org-a"
PROJECT = "project-a"
DOC = "document-a"


def make_app():
    actors = {
        "owner": CollaborationActor("owner", ORG, "Owner"),
        "editor": CollaborationActor("editor", ORG, "Editor"),
    }
    permissions = {
        key: {PROJECT: frozenset({"VIEW", "COMMENT", "EDIT"})} for key in actors
    }
    auth = StaticCollaborationAuthorization(permissions, {key: ORG for key in actors})
    repo = InMemoryCollaborationRepository()
    presence = InMemoryPresenceStore()
    canonical = InMemoryCanonicalDesign()
    canonical.seed(PROJECT, DOC, "design-v4")
    engine = CollaborationEngine(
        authorization=auth,
        repository=repo,
        presence=presence,
        canonical_design=canonical,
        constraints=RecordingConstraintValidator(),
        audit=RecordingCollaborationAudit(),
        notifications=RecordingCollaborationNotifications(),
    )

    def actor_summary(key: str) -> dict[str, object]:
        value = actors[key]
        return {
            "actor_id": value.actor_id,
            "display_name": value.display_name,
            "actor_type": value.actor_type,
            "role": "OWNER" if key == "owner" else "EDITOR",
            "agent_run_id": value.agent_run_id,
        }

    def http_actor(request: Request) -> CollaborationActor:
        return actors[request.headers.get("x-test-actor", "owner")]

    def ws_actor(socket: WebSocket) -> CollaborationActor:
        return actors[socket.headers.get("x-test-actor", "owner")]

    def workspace_metadata(actor: CollaborationActor, project_id: str):
        assert project_id == PROJECT
        current = "owner" if actor.actor_id == "owner" else "editor"
        return CollaborationWorkspaceMetadata(
            document_id=DOC,
            artifact_version_id="artifact-v4",
            current_user=actor_summary(current),
            members=(actor_summary("owner"), actor_summary("editor")),
        )

    app = FastAPI()
    app.include_router(
        create_collaboration_router(
            engine=engine,
            resolve_http_context=http_actor,
            resolve_ws_context=ws_actor,
            resolve_workspace_metadata=workspace_metadata,
        )
    )
    return app, canonical


def test_workspace_and_exact_thread_anchor() -> None:
    app, _ = make_app()
    client = TestClient(app)
    initial = client.get(f"/api/v1/projects/{PROJECT}/collaboration")
    assert initial.status_code == 200
    payload = initial.json()
    assert payload["canonical_version_id"] == "design-v4"
    assert payload["artifact_version_id"] == "artifact-v4"
    assert payload["current_user"]["role"] == "OWNER"
    assert payload["realtime"]["presence_is_ephemeral"] is True

    response = client.post(
        f"/api/v1/projects/{PROJECT}/collaboration/threads",
        json={
            "body": "Please review this historical node.",
            "mention_actor_ids": ["editor"],
            "anchor": {
                "artifact_version_id": "artifact-v2",
                "design_document_version_id": "design-v2",
                "node_id": "deleted-node",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["anchor"]["design_document_version_id"] == "design-v2"


def test_http_operation_and_reconnect_conflict_keep_canonical_truth() -> None:
    app, canonical = make_app()
    client = TestClient(app)
    first = client.post(
        f"/api/v1/projects/{PROJECT}/documents/{DOC}/collaboration/operations",
        json={
            "base_version_id": "design-v4",
            "operations": [
                {
                    "operation_id": "remote-op",
                    "node_id": "hero-title",
                    "property_name": "text",
                    "value": "Remote",
                }
            ],
        },
    )
    assert first.json()["canonical_version_after"] == "design-v5"

    conflict = client.post(
        f"/api/v1/projects/{PROJECT}/documents/{DOC}/collaboration/reconnect",
        headers={"x-test-actor": "editor"},
        json={
            "base_version_id": "design-v4",
            "operations": [
                {
                    "operation_id": "local-op",
                    "node_id": "hero-title",
                    "property_name": "text",
                    "value": "Local buffered",
                }
            ],
        },
    )
    body = conflict.json()
    assert body["conflicts"][0]["local_operation"]["value"] == "Local buffered"
    assert canonical.current_version(PROJECT, DOC) == "design-v5"


def test_websocket_is_awareness_only_and_rejects_canonical_write() -> None:
    app, canonical = make_app()
    client = TestClient(app)
    with client.websocket_connect(
        f"/api/v1/projects/{PROJECT}/collaboration/ws?document_id={DOC}"
    ) as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "PRESENCE_SNAPSHOT"
        socket.send_json(
            {
                "type": "AWARENESS_UPDATE",
                "cursor": [12, 20],
                "selection_ids": ["hero-title"],
            }
        )
        awareness = socket.receive_json()
        assert awareness["type"] == "AWARENESS_UPDATE"
        socket.send_json(
            {
                "type": "DESIGN_OPERATION",
                "operation_id": "must-not-run",
                "node_id": "hero-title",
                "property_name": "text",
                "value": "Forbidden transport write",
            }
        )
        rejected = socket.receive_json()
        assert rejected == {
            "type": "WRITE_REJECTED",
            "code": "COLLABORATION_CANONICAL_WRITE_REQUIRES_HTTP_OPERATION_API",
        }
    assert canonical.current_version(PROJECT, DOC) == "design-v4"
