from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lumi_api.collaboration.contracts import ThreadStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCommentThreadRequest(ApiModel):
    artifact_version_id: UUID
    design_node_id: UUID | None = None
    x: float | None = None
    y: float | None = None
    body: str = Field(min_length=1, max_length=20_000)
    mention_user_ids: tuple[UUID, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def validate_anchor_and_mentions(self) -> "CreateCommentThreadRequest":
        if (self.x is None) != (self.y is None):
            raise ValueError("thread anchor x/y must be both present or both absent")
        if len(self.mention_user_ids) != len(set(self.mention_user_ids)):
            raise ValueError("mention_user_ids must be unique")
        return self


class CreateCommentRequest(ApiModel):
    body: str = Field(min_length=1, max_length=20_000)
    mention_user_ids: tuple[UUID, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def mentions_unique(self) -> "CreateCommentRequest":
        if len(self.mention_user_ids) != len(set(self.mention_user_ids)):
            raise ValueError("mention_user_ids must be unique")
        return self


class EditCommentRequest(CreateCommentRequest):
    pass


class ThreadStatusRequest(ApiModel):
    status: ThreadStatus


class PresenceHeartbeatRequest(ApiModel):
    display_name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_000)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    artifact_version_id: UUID | None = None
    current_frame_id: UUID | None = None
    cursor_x: float | None = None
    cursor_y: float | None = None
    selection_node_ids: tuple[UUID, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def cursor_and_selection_valid(self) -> "PresenceHeartbeatRequest":
        if (self.cursor_x is None) != (self.cursor_y is None):
            raise ValueError("cursor x/y must be both present or both absent")
        if len(self.selection_node_ids) != len(set(self.selection_node_ids)):
            raise ValueError("selection_node_ids must be unique")
        return self
