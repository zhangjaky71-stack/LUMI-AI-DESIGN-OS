from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from .contracts import CollaborationAccess, ProjectRole, ThreadStatus
from .postgres_repository import (
    CollaborationForbidden,
    CollaborationNotFound,
    PostgresCollaborationRepository as _TransactionalRepository,
)


class PostgresCollaborationRepository(_TransactionalRepository):
    """Canonical NODE-61 repository facade with project-membership fail-closed access."""

    def get_access(
        self, *, organization_id: UUID, project_id: UUID, actor_id: str
    ) -> CollaborationAccess:
        self._assert_org(organization_id)
        actor_uuid = self._actor_uuid(actor_id)
        row = self.session.execute(
            text(
                """
                SELECT p.id AS project_id, p.created_by,
                       pm.role AS project_role,
                       om.role AS organization_role
                FROM projects p
                JOIN organization_members om
                  ON om.organization_id=p.organization_id
                 AND om.user_id=:actor_uuid
                LEFT JOIN project_members pm
                  ON pm.organization_id=p.organization_id
                 AND pm.project_id=p.id
                 AND pm.user_id=:actor_uuid
                WHERE p.id=:project_id
                  AND p.organization_id=:organization_id
                  AND p.deleted_at IS NULL
                """
            ),
            {
                "actor_uuid": actor_uuid,
                "project_id": project_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise CollaborationNotFound("PROJECT_NOT_FOUND")
        role_raw = row["project_role"]
        if row["created_by"] == actor_uuid:
            role = ProjectRole.ADMIN
        elif role_raw in {"admin", "editor", "viewer"}:
            role = ProjectRole(str(role_raw))
        else:
            raise CollaborationForbidden("PROJECT_MEMBERSHIP_REQUIRED")
        return CollaborationAccess(
            project_id=project_id,
            actor_id=actor_id,
            role=role,
            can_comment=True,
            can_edit_design=role in {ProjectRole.ADMIN, ProjectRole.EDITOR},
        )

    def require_project_artifact_version(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_version_id: UUID,
    ) -> UUID:
        self._assert_org(organization_id)
        artifact_id = self.session.execute(
            text(
                """
                SELECT a.id
                FROM artifact_versions av
                JOIN artifacts a
                  ON a.id=av.artifact_id
                 AND a.organization_id=av.organization_id
                WHERE av.id=:artifact_version_id
                  AND av.organization_id=:organization_id
                  AND a.project_id=:project_id
                  AND a.deleted_at IS NULL
                """
            ),
            {
                "artifact_version_id": artifact_version_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        ).scalar_one_or_none()
        if artifact_id is None:
            raise CollaborationNotFound("ARTIFACT_VERSION_NOT_FOUND")
        return artifact_id

    def _validate_mentions(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        mention_user_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if len(mention_user_ids) != len(set(mention_user_ids)):
            raise ValueError("MENTION_USER_IDS_MUST_BE_UNIQUE")
        if not mention_user_ids:
            return ()
        rows = self.session.execute(
            text(
                """
                SELECT om.user_id
                FROM organization_members om
                JOIN projects p
                  ON p.id=:project_id
                 AND p.organization_id=om.organization_id
                 AND p.deleted_at IS NULL
                LEFT JOIN project_members pm
                  ON pm.organization_id=p.organization_id
                 AND pm.project_id=p.id
                 AND pm.user_id=om.user_id
                WHERE om.organization_id=:organization_id
                  AND om.user_id = ANY(:user_ids)
                  AND (pm.user_id IS NOT NULL OR p.created_by=om.user_id)
                """
            ),
            {
                "project_id": project_id,
                "organization_id": organization_id,
                "user_ids": list(mention_user_ids),
            },
        ).scalars().all()
        valid = set(rows)
        if valid != set(mention_user_ids):
            raise CollaborationForbidden("MENTIONED_USER_PROJECT_ACCESS_REQUIRED")
        return tuple(sorted(valid, key=str))

    def set_thread_status(
        self,
        *,
        organization_id: UUID,
        thread_id: UUID,
        status: ThreadStatus,
        actor_id: str,
    ):
        self._assert_org(organization_id)
        with self._transaction():
            row = self._thread_for_update(organization_id, thread_id)
            access = self.get_access(
                organization_id=organization_id,
                project_id=row["project_id"],
                actor_id=actor_id,
            )
            if row["created_by"] != actor_id and access.role not in {
                ProjectRole.ADMIN,
                ProjectRole.EDITOR,
            }:
                raise CollaborationForbidden("THREAD_OWNER_OR_EDITOR_REQUIRED")
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            self.session.execute(
                text(
                    """
                    UPDATE comment_threads
                    SET status=:status,
                        resolved_by=:resolved_by,
                        resolved_at=:resolved_at
                    WHERE id=:thread_id AND organization_id=:organization_id
                    """
                ),
                {
                    "status": status.value,
                    "resolved_by": actor_id if status == ThreadStatus.RESOLVED else None,
                    "resolved_at": now if status == ThreadStatus.RESOLVED else None,
                    "thread_id": thread_id,
                    "organization_id": organization_id,
                },
            )
        row = self.session.execute(
            text("SELECT * FROM comment_threads WHERE id=:id AND organization_id=:org"),
            {"id": thread_id, "org": organization_id},
        ).mappings().one()
        return self._thread(row)
