from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollaborationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ThreadStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ProjectRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class CollaborationAccess(CollaborationModel):
    project_id: UUID
    actor_id: str = Field(min_length=1, max_length=200)
    role: ProjectRole
    can_comment: bool
    can_edit_design: bool


class CommentThread(CollaborationModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    artifact_id: UUID
    artifact_version_id: UUID
    design_node_id: UUID | None = None
    x: float | None = None
    y: float | None = None
    status: ThreadStatus
    needs_reanchor: bool = False
    created_by: str = Field(min_length=1, max_length=200)
    created_at: datetime
    resolved_by: str | None = Field(default=None, max_length=200)
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def anchor_and_resolution_are_consistent(self) -> "CommentThread":
        if (self.x is None) != (self.y is None):
            raise ValueError("thread anchor x/y must be both present or both absent")
        if self.status == ThreadStatus.RESOLVED and (
            self.resolved_by is None or self.resolved_at is None
        ):
            raise ValueError("resolved thread requires resolver and timestamp")
        if self.status == ThreadStatus.OPEN and (
            self.resolved_by is not None or self.resolved_at is not None
        ):
            raise ValueError("open thread cannot carry resolution metadata")
        return self


class Comment(CollaborationModel):
    id: UUID
    organization_id: UUID
    thread_id: UUID
    body: str = Field(min_length=1, max_length=20_000)
    mention_user_ids: tuple[UUID, ...] = ()
    created_by: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1)
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None

    @model_validator(mode="after")
    def mentions_unique(self) -> "Comment":
        if len(self.mention_user_ids) != len(set(self.mention_user_ids)):
            raise ValueError("mentioned user ids must be unique")
        return self


class CommentRevision(CollaborationModel):
    id: UUID
    organization_id: UUID
    comment_id: UUID
    revision_number: int = Field(ge=1)
    action: str = Field(pattern=r"^(CREATED|EDITED|DELETED)$")
    body_snapshot: str = Field(max_length=20_000)
    mention_user_ids: tuple[UUID, ...] = ()
    actor_id: str = Field(min_length=1, max_length=200)
    created_at: datetime


class CommentThreadBundle(CollaborationModel):
    thread: CommentThread
    comments: tuple[Comment, ...]


class PresenceState(CollaborationModel):
    user_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_000)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    project_id: UUID
    artifact_version_id: UUID | None = None
    current_frame_id: UUID | None = None
    cursor_x: float | None = None
    cursor_y: float | None = None
    selection_node_ids: tuple[UUID, ...] = Field(default=(), max_length=256)
    last_seen_at: datetime

    @model_validator(mode="after")
    def cursor_pair(self) -> "PresenceState":
        if (self.cursor_x is None) != (self.cursor_y is None):
            raise ValueError("presence cursor x/y must be both present or both absent")
        if len(self.selection_node_ids) != len(set(self.selection_node_ids)):
            raise ValueError("presence selection ids must be unique")
        return self
