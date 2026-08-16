# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TenantMixin, UUIDPrimaryKeyMixin


class ProjectBranchDefaultModel(Base, UUIDPrimaryKeyMixin, TenantMixin, CreatedAtMixin):
    __tablename__ = "project_branch_defaults"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, server_default="main")
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_branch_defaults_project"),
    )


class AgentRunProjectContextModel(Base, TenantMixin, CreatedAtMixin):
    __tablename__ = "agent_run_project_context"

    agent_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    project_brief_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("project_brief_version > 0", name="brief_version_positive"),
    )
