from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterator, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    CollaborationAccess,
    Comment,
    CommentRevision,
    CommentThread,
    CommentThreadBundle,
    ProjectRole,
    ThreadStatus,
)


class CollaborationNotFound(RuntimeError):
    pass


class CollaborationForbidden(RuntimeError):
    pass


class CollaborationConflict(RuntimeError):
    pass


class PostgresCollaborationRepository:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def _assert_org(self, organization_id: UUID) -> None:
        if organization_id != self.organization_id:
            raise CollaborationNotFound("COLLABORATION_RESOURCE_NOT_FOUND")

    @staticmethod
    def _actor_uuid(actor_id: str) -> UUID:
        try:
            return UUID(actor_id)
        except ValueError as exc:
            raise CollaborationForbidden("COLLABORATION_USER_ACTOR_REQUIRED") from exc

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
                  AND om.deleted_at IS NULL
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

    def require_exact_version(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
        artifact_version_id: UUID,
    ) -> None:
        self._assert_org(organization_id)
        exists = self.session.execute(
            text(
                """
                SELECT 1
                FROM artifact_versions av
                JOIN artifacts a
                  ON a.id=av.artifact_id
                 AND a.organization_id=av.organization_id
                WHERE av.id=:artifact_version_id
                  AND av.organization_id=:organization_id
                  AND a.id=:artifact_id
                  AND a.project_id=:project_id
                  AND a.deleted_at IS NULL
                """
            ),
            {
                "artifact_version_id": artifact_version_id,
                "organization_id": organization_id,
                "artifact_id": artifact_id,
                "project_id": project_id,
            },
        ).scalar_one_or_none()
        if exists is None:
            raise CollaborationNotFound("ARTIFACT_VERSION_NOT_FOUND")

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
        self._assert_org(organization_id)
        if (x is None) != (y is None):
            raise ValueError("THREAD_ANCHOR_COORDINATES_MUST_BE_PAIRED")
        now = datetime.now(UTC)
        thread_id = new_uuid7()
        comment_id = new_uuid7()
        with self._transaction():
            access = self.get_access(
                organization_id=organization_id,
                project_id=project_id,
                actor_id=actor_id,
            )
            if not access.can_comment:
                raise CollaborationForbidden("COMMENT_PERMISSION_REQUIRED")
            self.require_exact_version(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact_id,
                artifact_version_id=artifact_version_id,
            )
            mentions = self._validate_mentions(
                organization_id=organization_id,
                project_id=project_id,
                mention_user_ids=mention_user_ids,
            )
            self.session.execute(
                text(
                    """
                    INSERT INTO comment_threads (
                        id, organization_id, project_id, artifact_id,
                        artifact_version_id, design_node_id, x, y, status,
                        needs_reanchor, created_by, created_at
                    ) VALUES (
                        :id, :organization_id, :project_id, :artifact_id,
                        :artifact_version_id, :design_node_id, :x, :y, 'OPEN',
                        false, :created_by, :created_at
                    )
                    """
                ),
                {
                    "id": thread_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "artifact_id": artifact_id,
                    "artifact_version_id": artifact_version_id,
                    "design_node_id": design_node_id,
                    "x": x,
                    "y": y,
                    "created_by": actor_id,
                    "created_at": now,
                },
            )
            self._insert_comment(
                organization_id=organization_id,
                comment_id=comment_id,
                thread_id=thread_id,
                body=body,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
            self._emit_mentions(
                organization_id=organization_id,
                project_id=project_id,
                thread_id=thread_id,
                comment_id=comment_id,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
        return self.get_thread_bundle(
            organization_id=organization_id,
            thread_id=thread_id,
            actor_id=actor_id,
        )

    def list_threads(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_id: UUID,
        current_artifact_version_id: UUID,
        actor_id: str,
        include_history: bool = False,
        include_resolved: bool = True,
    ) -> tuple[CommentThreadBundle, ...]:
        self._assert_org(organization_id)
        self.get_access(
            organization_id=organization_id, project_id=project_id, actor_id=actor_id
        )
        self.require_exact_version(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version_id=current_artifact_version_id,
        )
        clauses = [
            "organization_id=:organization_id",
            "project_id=:project_id",
            "artifact_id=:artifact_id",
        ]
        if not include_history:
            clauses.append("artifact_version_id=:current_artifact_version_id")
        if not include_resolved:
            clauses.append("status='OPEN'")
        rows = self.session.execute(
            text(
                f"""
                SELECT * FROM comment_threads
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at, id
                """
            ),
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "artifact_id": artifact_id,
                "current_artifact_version_id": current_artifact_version_id,
            },
        ).mappings().all()
        return tuple(
            CommentThreadBundle(
                thread=self._thread(
                    row,
                    needs_reanchor=(
                        bool(row["needs_reanchor"])
                        or row["artifact_version_id"] != current_artifact_version_id
                    ),
                ),
                comments=self._comments(organization_id, row["id"]),
            )
            for row in rows
        )

    def get_thread_bundle(
        self, *, organization_id: UUID, thread_id: UUID, actor_id: str
    ) -> CommentThreadBundle:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(
                """
                SELECT * FROM comment_threads
                WHERE id=:thread_id AND organization_id=:organization_id
                """
            ),
            {"thread_id": thread_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise CollaborationNotFound("COMMENT_THREAD_NOT_FOUND")
        self.get_access(
            organization_id=organization_id,
            project_id=row["project_id"],
            actor_id=actor_id,
        )
        return CommentThreadBundle(
            thread=self._thread(row), comments=self._comments(organization_id, thread_id)
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
        self._assert_org(organization_id)
        comment_id = new_uuid7()
        now = datetime.now(UTC)
        with self._transaction():
            thread = self._thread_for_update(organization_id, thread_id)
            access = self.get_access(
                organization_id=organization_id,
                project_id=thread["project_id"],
                actor_id=actor_id,
            )
            if not access.can_comment:
                raise CollaborationForbidden("COMMENT_PERMISSION_REQUIRED")
            mentions = self._validate_mentions(
                organization_id=organization_id,
                project_id=thread["project_id"],
                mention_user_ids=mention_user_ids,
            )
            self._insert_comment(
                organization_id=organization_id,
                comment_id=comment_id,
                thread_id=thread_id,
                body=body,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
            self._emit_mentions(
                organization_id=organization_id,
                project_id=thread["project_id"],
                thread_id=thread_id,
                comment_id=comment_id,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
        return self._comment_by_id(organization_id, comment_id)

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
        self._assert_org(organization_id)
        now = datetime.now(UTC)
        with self._transaction():
            row = self._comment_for_update(organization_id, comment_id)
            thread = self._thread_for_update(organization_id, row["thread_id"])
            access = self.get_access(
                organization_id=organization_id,
                project_id=thread["project_id"],
                actor_id=actor_id,
            )
            if row["deleted_at"] is not None:
                raise CollaborationConflict("COMMENT_DELETED")
            if int(row["revision"]) != expected_revision:
                raise CollaborationConflict("COMMENT_REVISION_CONFLICT")
            if row["created_by"] != actor_id and access.role != ProjectRole.ADMIN:
                raise CollaborationForbidden("COMMENT_OWNER_OR_ADMIN_REQUIRED")
            mentions = self._validate_mentions(
                organization_id=organization_id,
                project_id=thread["project_id"],
                mention_user_ids=mention_user_ids,
            )
            revision = expected_revision + 1
            self.session.execute(
                text(
                    """
                    UPDATE comments
                    SET body=:body, mentions_json=CAST(:mentions AS jsonb),
                        edited_at=:edited_at, revision=:revision
                    WHERE id=:comment_id AND organization_id=:organization_id
                    """
                ),
                {
                    "body": body,
                    "mentions": self._json_ids(mentions),
                    "edited_at": now,
                    "revision": revision,
                    "comment_id": comment_id,
                    "organization_id": organization_id,
                },
            )
            self._insert_revision(
                organization_id=organization_id,
                comment_id=comment_id,
                revision_number=revision,
                action="EDITED",
                body=body,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
            self._emit_mentions(
                organization_id=organization_id,
                project_id=thread["project_id"],
                thread_id=row["thread_id"],
                comment_id=comment_id,
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
        return self._comment_by_id(organization_id, comment_id)

    def delete_comment(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        expected_revision: int,
        actor_id: str,
    ) -> Comment:
        self._assert_org(organization_id)
        now = datetime.now(UTC)
        with self._transaction():
            row = self._comment_for_update(organization_id, comment_id)
            thread = self._thread_for_update(organization_id, row["thread_id"])
            access = self.get_access(
                organization_id=organization_id,
                project_id=thread["project_id"],
                actor_id=actor_id,
            )
            if row["deleted_at"] is not None:
                raise CollaborationConflict("COMMENT_ALREADY_DELETED")
            if int(row["revision"]) != expected_revision:
                raise CollaborationConflict("COMMENT_REVISION_CONFLICT")
            if row["created_by"] != actor_id and access.role != ProjectRole.ADMIN:
                raise CollaborationForbidden("COMMENT_OWNER_OR_ADMIN_REQUIRED")
            revision = expected_revision + 1
            mentions = self._mention_ids(row["mentions_json"])
            self.session.execute(
                text(
                    """
                    UPDATE comments
                    SET deleted_at=:deleted_at, revision=:revision
                    WHERE id=:comment_id AND organization_id=:organization_id
                    """
                ),
                {
                    "deleted_at": now,
                    "revision": revision,
                    "comment_id": comment_id,
                    "organization_id": organization_id,
                },
            )
            self._insert_revision(
                organization_id=organization_id,
                comment_id=comment_id,
                revision_number=revision,
                action="DELETED",
                body=str(row["body"]),
                mentions=mentions,
                actor_id=actor_id,
                now=now,
            )
        return self._comment_by_id(organization_id, comment_id)

    def set_thread_status(
        self,
        *,
        organization_id: UUID,
        thread_id: UUID,
        status: ThreadStatus,
        actor_id: str,
    ) -> CommentThread:
        self._assert_org(organization_id)
        now = datetime.now(UTC)
        with self._transaction():
            row = self._thread_for_update(organization_id, thread_id)
            self.get_access(
                organization_id=organization_id,
                project_id=row["project_id"],
                actor_id=actor_id,
            )
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

    def list_comment_revisions(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        actor_id: str,
    ) -> tuple[CommentRevision, ...]:
        self._assert_org(organization_id)
        comment = self.session.execute(
            text(
                """
                SELECT c.*, t.project_id
                FROM comments c JOIN comment_threads t ON t.id=c.thread_id
                WHERE c.id=:comment_id AND c.organization_id=:organization_id
                """
            ),
            {"comment_id": comment_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if comment is None:
            raise CollaborationNotFound("COMMENT_NOT_FOUND")
        access = self.get_access(
            organization_id=organization_id,
            project_id=comment["project_id"],
            actor_id=actor_id,
        )
        if comment["created_by"] != actor_id and access.role != ProjectRole.ADMIN:
            raise CollaborationForbidden("COMMENT_AUDIT_OWNER_OR_ADMIN_REQUIRED")
        rows = self.session.execute(
            text(
                """
                SELECT * FROM comment_revisions
                WHERE organization_id=:organization_id AND comment_id=:comment_id
                ORDER BY revision_number
                """
            ),
            {"organization_id": organization_id, "comment_id": comment_id},
        ).mappings().all()
        return tuple(self._revision(row) for row in rows)

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
                  AND om.deleted_at IS NULL
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

    def _insert_comment(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        thread_id: UUID,
        body: str,
        mentions: tuple[UUID, ...],
        actor_id: str,
        now: datetime,
    ) -> None:
        normalized = body.strip()
        if not normalized:
            raise ValueError("COMMENT_BODY_REQUIRED")
        if len(normalized) > 20_000:
            raise ValueError("COMMENT_BODY_TOO_LONG")
        self.session.execute(
            text(
                """
                INSERT INTO comments (
                    id, organization_id, thread_id, body, mentions_json,
                    created_by, revision, created_at
                ) VALUES (
                    :id, :organization_id, :thread_id, :body,
                    CAST(:mentions AS jsonb), :created_by, 1, :created_at
                )
                """
            ),
            {
                "id": comment_id,
                "organization_id": organization_id,
                "thread_id": thread_id,
                "body": normalized,
                "mentions": self._json_ids(mentions),
                "created_by": actor_id,
                "created_at": now,
            },
        )
        self._insert_revision(
            organization_id=organization_id,
            comment_id=comment_id,
            revision_number=1,
            action="CREATED",
            body=normalized,
            mentions=mentions,
            actor_id=actor_id,
            now=now,
        )

    def _insert_revision(
        self,
        *,
        organization_id: UUID,
        comment_id: UUID,
        revision_number: int,
        action: str,
        body: str,
        mentions: tuple[UUID, ...],
        actor_id: str,
        now: datetime,
    ) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO comment_revisions (
                    id, organization_id, comment_id, revision_number, action,
                    body_snapshot, mentions_json, actor_id, metadata_json, created_at
                ) VALUES (
                    :id, :organization_id, :comment_id, :revision_number, :action,
                    :body_snapshot, CAST(:mentions AS jsonb), :actor_id,
                    '{}'::jsonb, :created_at
                )
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": organization_id,
                "comment_id": comment_id,
                "revision_number": revision_number,
                "action": action,
                "body_snapshot": body,
                "mentions": self._json_ids(mentions),
                "actor_id": actor_id,
                "created_at": now,
            },
        )

    def _emit_mentions(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        thread_id: UUID,
        comment_id: UUID,
        mentions: tuple[UUID, ...],
        actor_id: str,
        now: datetime,
    ) -> None:
        actor_uuid = self._actor_uuid(actor_id)
        for user_id in mentions:
            if user_id == actor_uuid:
                continue
            payload = json.dumps(
                {
                    "project_id": str(project_id),
                    "thread_id": str(thread_id),
                    "comment_id": str(comment_id),
                    "mentioned_user_id": str(user_id),
                    "actor_id": actor_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.session.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                        id, organization_id, event_type, aggregate_type,
                        aggregate_id, payload_json, occurred_at, created_at
                    ) VALUES (
                        :id, :organization_id, 'collaboration.comment.mentioned',
                        'comment', :aggregate_id, CAST(:payload AS jsonb),
                        :occurred_at, :created_at
                    )
                    """
                ),
                {
                    "id": new_uuid7(),
                    "organization_id": organization_id,
                    "aggregate_id": comment_id,
                    "payload": payload,
                    "occurred_at": now,
                    "created_at": now,
                },
            )

    def _thread_for_update(self, organization_id: UUID, thread_id: UUID) -> Mapping[str, Any]:
        row = self.session.execute(
            text(
                "SELECT * FROM comment_threads WHERE id=:id AND organization_id=:org FOR UPDATE"
            ),
            {"id": thread_id, "org": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise CollaborationNotFound("COMMENT_THREAD_NOT_FOUND")
        return row

    def _comment_for_update(self, organization_id: UUID, comment_id: UUID) -> Mapping[str, Any]:
        row = self.session.execute(
            text(
                "SELECT * FROM comments WHERE id=:id AND organization_id=:org FOR UPDATE"
            ),
            {"id": comment_id, "org": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise CollaborationNotFound("COMMENT_NOT_FOUND")
        return row

    def _comments(self, organization_id: UUID, thread_id: UUID) -> tuple[Comment, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT * FROM comments
                WHERE organization_id=:organization_id AND thread_id=:thread_id
                ORDER BY created_at, id
                """
            ),
            {"organization_id": organization_id, "thread_id": thread_id},
        ).mappings().all()
        return tuple(self._comment(row) for row in rows)

    def _comment_by_id(self, organization_id: UUID, comment_id: UUID) -> Comment:
        row = self.session.execute(
            text("SELECT * FROM comments WHERE id=:id AND organization_id=:org"),
            {"id": comment_id, "org": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise CollaborationNotFound("COMMENT_NOT_FOUND")
        return self._comment(row)

    @staticmethod
    def _thread(row: Mapping[str, Any], *, needs_reanchor: bool | None = None) -> CommentThread:
        return CommentThread(
            id=row["id"],
            organization_id=row["organization_id"],
            project_id=row["project_id"],
            artifact_id=row["artifact_id"],
            artifact_version_id=row["artifact_version_id"],
            design_node_id=row["design_node_id"],
            x=float(row["x"]) if row["x"] is not None else None,
            y=float(row["y"]) if row["y"] is not None else None,
            status=ThreadStatus(str(row["status"])),
            needs_reanchor=bool(row["needs_reanchor"]) if needs_reanchor is None else needs_reanchor,
            created_by=row["created_by"],
            created_at=row["created_at"],
            resolved_by=row["resolved_by"],
            resolved_at=row["resolved_at"],
        )

    @staticmethod
    def _comment(row: Mapping[str, Any]) -> Comment:
        deleted = row["deleted_at"] is not None
        return Comment(
            id=row["id"],
            organization_id=row["organization_id"],
            thread_id=row["thread_id"],
            body="[deleted]" if deleted else str(row["body"]),
            mention_user_ids=PostgresCollaborationRepository._mention_ids(row["mentions_json"]),
            created_by=row["created_by"],
            revision=int(row["revision"]),
            created_at=row["created_at"],
            edited_at=row["edited_at"],
            deleted_at=row["deleted_at"],
        )

    @staticmethod
    def _revision(row: Mapping[str, Any]) -> CommentRevision:
        return CommentRevision(
            id=row["id"],
            organization_id=row["organization_id"],
            comment_id=row["comment_id"],
            revision_number=int(row["revision_number"]),
            action=row["action"],
            body_snapshot=str(row["body_snapshot"]),
            mention_user_ids=PostgresCollaborationRepository._mention_ids(row["mentions_json"]),
            actor_id=row["actor_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _mention_ids(value: Any) -> tuple[UUID, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(UUID(str(item)) for item in value)

    @staticmethod
    def _json_ids(values: tuple[UUID, ...]) -> str:
        return json.dumps([str(item) for item in values], separators=(",", ":"))
