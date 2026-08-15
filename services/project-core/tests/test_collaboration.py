from __future__ import annotations

import pytest

from lumi_project_core.collaboration import (
    CollaborationActor,
    CollaborationEngine,
    CollaborationError,
    CollaborationOperation,
    CommentAnchor,
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


def actor(actor_id: str, *, agent: bool = False) -> CollaborationActor:
    return CollaborationActor(
        actor_id=actor_id,
        organization_id=ORG,
        display_name=actor_id,
        actor_type="AGENT" if agent else "USER",
        agent_run_id="run-agent-61" if agent else None,
    )


def setup_engine(*, forbidden: frozenset[str] = frozenset()):
    people = ["owner", "editor", "viewer", "agent"]
    permissions = {
        "owner": {PROJECT: frozenset({"VIEW", "COMMENT", "EDIT"})},
        "editor": {PROJECT: frozenset({"VIEW", "COMMENT", "EDIT"})},
        "viewer": {PROJECT: frozenset({"VIEW", "COMMENT"})},
        "agent": {PROJECT: frozenset({"VIEW", "COMMENT", "EDIT"})},
    }
    auth = StaticCollaborationAuthorization(permissions, {item: ORG for item in people})
    repo = InMemoryCollaborationRepository()
    presence = InMemoryPresenceStore()
    canonical = InMemoryCanonicalDesign()
    canonical.seed(PROJECT, DOC, "design-v4")
    constraints = RecordingConstraintValidator(forbidden)
    audit = RecordingCollaborationAudit()
    notifications = RecordingCollaborationNotifications()
    engine = CollaborationEngine(
        authorization=auth,
        repository=repo,
        presence=presence,
        canonical_design=canonical,
        constraints=constraints,
        audit=audit,
        notifications=notifications,
    )
    return engine, repo, presence, canonical, constraints, audit, notifications


def op(operation_id: str, node: str, prop: str, value: object) -> CollaborationOperation:
    return CollaborationOperation(operation_id, node, prop, value)


def test_two_users_different_nodes_rebase_without_lost_update() -> None:
    engine, _, _, canonical, constraints, _, _ = setup_engine()
    first = engine.submit_operations(actor("owner"), PROJECT, DOC, "design-v4", (
        op("op-a", "hero-title", "text", "New title"),
    ))
    assert first.canonical_version_after == "design-v5"

    second = engine.submit_operations(actor("editor"), PROJECT, DOC, "design-v4", (
        op("op-b", "cta", "fill", "#111111"),
    ))
    assert second.rebased is True
    assert second.conflicts == ()
    assert second.accepted_operation_ids == ("op-b",)
    assert second.canonical_version_after == "design-v6"
    assert canonical.current_version(PROJECT, DOC) == "design-v6"
    assert len(constraints.calls) == 2


def test_same_property_conflict_is_explicit_and_local_edit_is_preserved() -> None:
    engine, _, _, canonical, _, audit, _ = setup_engine()
    engine.submit_operations(actor("owner"), PROJECT, DOC, "design-v4", (
        op("remote-op", "hero-title", "text", "Remote"),
    ))
    result = engine.reconnect(actor("editor"), PROJECT, DOC, "design-v4", (
        op("local-op", "hero-title", "text", "Local buffered"),
    ))
    assert result.rebased is True
    assert result.accepted_operation_ids == ()
    assert len(result.conflicts) == 1
    assert result.conflicts[0].local_operation.value == "Local buffered"
    assert result.conflicts[0].remote_operation_id == "remote-op"
    assert canonical.current_version(PROJECT, DOC) == "design-v5"
    assert any(event.metadata.get("local_edit_preserved") is True for event in audit.events)


def test_presence_is_ephemeral_and_tenant_isolated() -> None:
    engine, _, presence, _, _, _, _ = setup_engine()
    engine.update_presence(actor("owner"), PROJECT, DOC, cursor=(10.0, 20.0), selection_ids=("hero",))
    assert [item.actor.actor_id for item in engine.list_presence(actor("viewer"), PROJECT, DOC)] == ["owner"]

    outsider = CollaborationActor("outsider", "org-b", "outsider")
    with pytest.raises(CollaborationError, match="COLLABORATION_FORBIDDEN"):
        engine.list_presence(outsider, PROJECT, DOC)
    assert len(presence.states) == 1


def test_comment_keeps_exact_old_version_context_after_design_advances() -> None:
    engine, repo, _, canonical, _, _, _ = setup_engine()
    thread = engine.create_thread(
        actor("viewer"),
        CommentAnchor(PROJECT, "artifact-version-v2", "design-v2", node_id="deleted-node"),
        "This belongs to the historical layout.",
    )
    engine.submit_operations(actor("owner"), PROJECT, DOC, "design-v4", (
        op("op-new", "hero", "opacity", 0.9),
    ))
    stored = repo.get_thread(ORG, PROJECT, thread.thread_id)
    assert stored is not None
    assert stored.anchor.design_document_version_id == "design-v2"
    assert stored.anchor.node_id == "deleted-node"
    assert canonical.current_version(PROJECT, DOC) == "design-v5"


def test_mention_requires_target_access_to_same_project() -> None:
    engine, _, _, _, _, _, _ = setup_engine()
    with pytest.raises(CollaborationError, match="COLLABORATION_MENTION_FORBIDDEN"):
        engine.create_thread(
            actor("viewer"),
            CommentAnchor(PROJECT, "artifact-v4", "design-v4"),
            "Please review",
            ("not-a-member",),
        )


def test_hard_constraint_failure_blocks_canonical_commit() -> None:
    engine, _, _, canonical, constraints, _, _ = setup_engine(forbidden=frozenset({"logo.identity"}))
    with pytest.raises(CollaborationError, match="COLLABORATION_HARD_CONSTRAINT_FAILED"):
        engine.submit_operations(actor("editor"), PROJECT, DOC, "design-v4", (
            op("op-logo", "logo", "logo.identity", "mutate-protected-mark"),
        ))
    assert canonical.current_version(PROJECT, DOC) == "design-v4"
    assert len(constraints.calls) == 1


def test_agent_actor_requires_run_id_and_is_distinguishable_in_audit() -> None:
    with pytest.raises(CollaborationError, match="COLLABORATION_AGENT_RUN_REQUIRED"):
        CollaborationActor("agent", ORG, "LUMI", actor_type="AGENT")

    engine, _, _, _, _, audit, _ = setup_engine()
    thread = engine.create_thread(
        actor("agent", agent=True),
        CommentAnchor(PROJECT, "artifact-v4", "design-v4", node_id="hero"),
        "I checked the requested revision.",
    )
    event = next(item for item in audit.events if item.target_id == thread.thread_id)
    assert event.actor_type == "AGENT"
    assert event.agent_run_id == "run-agent-61"


def test_realtime_restart_does_not_erase_canonical_truth() -> None:
    engine, repo, presence, canonical, constraints, audit, notifications = setup_engine()
    thread = engine.create_thread(
        actor("owner"),
        CommentAnchor(PROJECT, "artifact-v4", "design-v4"),
        "Persist this review context.",
    )
    engine.update_presence(actor("owner"), PROJECT, DOC)
    engine.submit_operations(actor("owner"), PROJECT, DOC, "design-v4", (
        op("op-persist", "hero", "fill", "#222222"),
    ))

    restarted = CollaborationEngine(
        authorization=engine._authorization,
        repository=repo,
        presence=InMemoryPresenceStore(),
        canonical_design=canonical,
        constraints=constraints,
        audit=audit,
        notifications=notifications,
    )
    assert restarted.list_presence(actor("owner"), PROJECT, DOC) == ()
    assert restarted.workspace(actor("owner"), PROJECT, DOC)["canonical_version_id"] == "design-v5"
    assert repo.get_thread(ORG, PROJECT, thread.thread_id) is not None
    assert len(presence.states) == 1
