# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .model_support import JSON_ARRAY_DEFAULT, JSON_OBJECT_DEFAULT


class AgentGraphDefinitionModel(Base):
    __tablename__ = "agent_graph_definitions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    graph_key: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_config_version: Mapped[str] = mapped_column(String(100), nullable=False)
    code_git_sha: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    state_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("graph_key", "graph_version", name="uq_agent_graph_definitions_identity"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="hash"),
        CheckConstraint("state_schema_version >= 1", name="schema_version"),
    )


class AgentRunControlModel(Base):
    __tablename__ = "agent_run_control"

    agent_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    graph_key: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(100), nullable=False)
    code_git_sha: Mapped[str] = mapped_column(String(80), nullable=False)
    graph_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    control_status: Mapped[str] = mapped_column(String(32), nullable=False)
    checkpoint_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checkpoint_namespace: Mapped[str] = mapped_column(String(1024), nullable=False, server_default="")
    state_values_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_OBJECT_DEFAULT
    )
    next_nodes_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    interrupts_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=JSON_ARRAY_DEFAULT
    )
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "thread_id", name="uq_agent_run_control_thread"
        ),
        CheckConstraint(
            "control_status IN ('pending','running','waiting_user','waiting_external',"
            "'cancel_requested','succeeded','failed','cancelled')",
            name="status",
        ),
        CheckConstraint("resume_version >= 1", name="resume_version"),
        CheckConstraint("version >= 1", name="version"),
    )
