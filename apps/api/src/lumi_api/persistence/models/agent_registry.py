from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AgentRunProvenance(Base):
    __tablename__ = "agent_run_provenance"

    agent_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exact_version: Mapped[str] = mapped_column(String(100), nullable=False)
    release_status: Mapped[str] = mapped_column(String(16), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    release_manifest_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dependencies_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
