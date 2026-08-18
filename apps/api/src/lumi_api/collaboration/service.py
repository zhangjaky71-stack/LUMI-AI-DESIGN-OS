from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from .contracts import (
    Comment,
    CommentRevision,
    CommentThread,
    CommentThreadBundle,
    PresenceState,
    ThreadStatus,
)
from .postgres_repository import PostgresCollaborationRepository
from .presence import PRESENCE_TTL_SECONDS, PresencePort


class CollaborationService:
    def __init__(
        self,
        repository: PostgresCollaborationRepository,
        presence: PresencePort,
    ) -> None:
        self.repository = repository
        self.presence = presence

    def list_threads(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
        current_artifact_version_id: UUID,
        actor_id: str,
        include_history: bool,
        include_resolved: bool,
    ) -> tuple[CommentThreadBundle, ...]:
        return self.repository.list_threads(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            current_artifact_version_id=current_artifact_version_id,
            actor_id=actor_id,
            include_history=include_history,
            include_resolved=include_resolved,
        )

    def create_thread(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
        artifact_version_id: UUID,
        design_node_id: UUID | None,
        x: float | None,
        y: float | None,
        body: str,
        mention_user_ids: tuple[UUID, ...],
        actor_id: str,
    ) -> CommentThreadBundle:
        return self.repository.create_thread(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            design_node_id=design_node_id,
            x=x,
            y=y,
            body=body,
            mention_user_ids=mention_user_ids,
            actor_id=actor_id,
        )

    def add_comment(
        self,
        *,
        organization_id: UUID,
        thread_id: UUID,
        body: str,
        mention_user_ids: tuple[UUID, ...],
        actor_id: str,
    ) -> Comment:
        return self.repository.add_comment(
            organization_id=organization_id,
            thread_id=thread_id,
            body=body,
            mention_user_ids=mention_user_ids,
            actor_id=actor_id,
        )

    def edit_comment(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        expected_revision: int,
        body: str,
        mention_user_ids: tuple[UUID, ...],
        actor_id: str,
    ) -> Comment:
        return self.repository.edit_comment(
            organization_id=organization_id,
            comment_id=comment_id,
            expected_revision=expected_revision,
            body=body,
            mention_user_ids=mention_user_ids,
            actor_id=actor_id,
        )

    def delete_comment(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        expected_revision: int,
        actor_id: str,
    ) -> Comment:
        return self.repository.delete_comment(
            organization_id=organization_id,
            comment_id=comment_id,
            expected_revision=expected_revision,
            actor_id=actor_id,
        )

    def set_thread_status(
        self,
        *,
        organization_id: UUID,
        thread_id: UUID,
        status: ThreadStatus,
        actor_id: str,
    ) -> CommentThread:
        return self.repository.set_thread_status(
            organization_id=organization_id,
            thread_id=thread_id,
            status=status,
            actor_id=actor_id,
        )

    def list_revisions(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        actor_id: str,
    ) -> tuple[CommentRevision, ...]:
        return self.repository.list_comment_revisions(
            organization_id=organization_id,
            comment_id=comment_id,
            actor_id=actor_id,
        )

    def heartbeat_presence(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_id: str,
        display_name: str,
        avatar_url: str | None,
        color: str,
        artifact_version_id: UUID | None,
        current_frame_id: UUID | None,
        cursor_x: float | None,
        cursor_y: float | None,
        selection_node_ids: tuple[UUID, ...],
    ) -> PresenceState:
        self.repository.get_access(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
        )
        if artifact_version_id is not None:
            artifact_row = self.repository.session.execute(
                __import__("sqlalchemy").text(
                    """
                    SELECT a.id
                    FROM artifact_versions av
                    JOIN artifacts a ON a.id=av.artifact_id AND a.organization_id=av.organization_id
                    WHERE av.id=:version_id
                      AND av.organization_id=:organization_id
                      AND a.project_id=:project_id
                      AND a.deleted_at IS NULL
                    """
                ),
                {
                    "version_id": artifact_version_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                },
            ).scalar_one_or_none()
            if artifact_row is None:
                from .postgres_repository import CollaborationNotFound

                raise CollaborationNotFound("ARTIFACT_VERSION_NOT_FOUND")
        value = PresenceState(
            user_id=actor_id,
            display_name=display_name.strip(),
            avatar_url=avatar_url,
            color=color,
            project_id=project_id,
            artifact_version_id=artifact_version_id,
            current_frame_id=current_frame_id,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            selection_node_ids=selection_node_ids,
            last_seen_at=datetime.now(UTC),
        )
        return self.presence.heartbeat(value, ttl_seconds=PRESENCE_TTL_SECONDS)

    def list_presence(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_id: str,
    ) -> tuple[PresenceState, ...]:
        self.repository.get_access(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
        )
        return self.presence.list_project(project_id)

    def leave_presence(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_id: str,
    ) -> None:
        self.repository.get_access(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
        )
        self.presence.remove(project_id, actor_id)
