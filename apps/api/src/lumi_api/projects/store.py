from __future__ import annotations

import base64
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .models import (
    BriefVersion,
    DefaultProjectBranch,
    ProjectEvent,
    ProjectListQuery,
    ProjectPage,
    ProjectRecord,
    ProjectSummary,
)


class ProjectRepository(Protocol):
    def get(self, organization_id: UUID, project_id: UUID) -> ProjectRecord | None: ...

    def list(self, query: ProjectListQuery) -> ProjectPage: ...

    def insert_creation_bundle(
        self,
        project: ProjectRecord,
        brief_version: BriefVersion,
        default_branch: DefaultProjectBranch,
        summary: ProjectSummary,
        events: tuple[ProjectEvent, ...],
    ) -> None: ...

    def update_project(
        self,
        project: ProjectRecord,
        *,
        expected_version: int,
        brief_version: BriefVersion | None,
        events: tuple[ProjectEvent, ...],
    ) -> None: ...

    def list_brief_versions(
        self, organization_id: UUID, project_id: UUID
    ) -> tuple[BriefVersion, ...]: ...


@dataclass(slots=True)
class MemoryProjectRepository(ProjectRepository):
    projects: dict[UUID, ProjectRecord] = field(default_factory=dict)
    briefs: dict[UUID, list[BriefVersion]] = field(default_factory=dict)
    branches: dict[UUID, DefaultProjectBranch] = field(default_factory=dict)
    summaries: dict[UUID, ProjectSummary] = field(default_factory=dict)
    outbox: list[ProjectEvent] = field(default_factory=list)

    def get(self, organization_id: UUID, project_id: UUID) -> ProjectRecord | None:
        project = self.projects.get(project_id)
        if project is None or project.organization_id != organization_id:
            return None
        return project

    @staticmethod
    def _encode_cursor(updated_at: datetime, project_id: UUID) -> str:
        raw = f"{updated_at.isoformat()}|{project_id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
        padding = "=" * (-len(cursor) % 4)
        try:
            raw = base64.urlsafe_b64decode(cursor + padding).decode()
            timestamp, project_id = raw.split("|", 1)
            return datetime.fromisoformat(timestamp), UUID(project_id)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("INVALID_PROJECT_CURSOR") from exc

    def list(self, query: ProjectListQuery) -> ProjectPage:
        rows: Iterable[ProjectRecord] = (
            project
            for project in self.projects.values()
            if project.organization_id == query.organization_id
        )
        if query.status is not None:
            rows = (project for project in rows if project.status == query.status)
        if query.workspace_id is not None:
            rows = (project for project in rows if project.workspace_id == query.workspace_id)
        if query.created_by is not None:
            rows = (project for project in rows if project.created_by == query.created_by)
        if query.updated_from is not None:
            rows = (project for project in rows if project.updated_at >= query.updated_from)
        if query.updated_to is not None:
            rows = (project for project in rows if project.updated_at <= query.updated_to)
        if query.name_query is not None:
            needle = query.name_query.casefold()
            rows = (project for project in rows if needle in project.name.casefold())

        ordered = sorted(rows, key=lambda p: (p.updated_at, p.id), reverse=True)
        if query.cursor:
            cursor_key = self._decode_cursor(query.cursor)
            ordered = [
                project
                for project in ordered
                if (project.updated_at, project.id) < cursor_key
            ]
        selected = ordered[: query.limit + 1]
        has_more = len(selected) > query.limit
        selected = selected[: query.limit]
        next_cursor = None
        if has_more and selected:
            tail = selected[-1]
            next_cursor = self._encode_cursor(tail.updated_at, tail.id)
        return ProjectPage(items=tuple(selected), next_cursor=next_cursor)

    def insert_creation_bundle(
        self,
        project: ProjectRecord,
        brief_version: BriefVersion,
        default_branch: DefaultProjectBranch,
        summary: ProjectSummary,
        events: tuple[ProjectEvent, ...],
    ) -> None:
        if project.id in self.projects:
            raise ValueError("PROJECT_ALREADY_EXISTS")
        if default_branch.project_id != project.id or summary.project_id != project.id:
            raise ValueError("PROJECT_BUNDLE_SCOPE_MISMATCH")
        snapshot = (
            dict(self.projects),
            {key: list(value) for key, value in self.briefs.items()},
            dict(self.branches),
            dict(self.summaries),
            list(self.outbox),
        )
        try:
            self.projects[project.id] = project
            self.briefs.setdefault(project.id, []).append(brief_version)
            self.branches[default_branch.id] = default_branch
            self.summaries[project.id] = summary
            self.outbox.extend(events)
        except Exception:
            self.projects, self.briefs, self.branches, self.summaries, self.outbox = snapshot
            raise

    def update_project(
        self,
        project: ProjectRecord,
        *,
        expected_version: int,
        brief_version: BriefVersion | None,
        events: tuple[ProjectEvent, ...],
    ) -> None:
        current = self.get(project.organization_id, project.id)
        if current is None:
            raise ValueError("PROJECT_NOT_FOUND")
        if current.version != expected_version:
            raise ValueError("PROJECT_VERSION_CONFLICT")
        if project.version != expected_version + 1:
            raise ValueError("PROJECT_VERSION_MUST_INCREMENT")
        self.projects[project.id] = project
        if brief_version is not None:
            history = self.briefs.setdefault(project.id, [])
            if history and brief_version.version != history[-1].version + 1:
                raise ValueError("BRIEF_VERSION_MUST_INCREMENT")
            history.append(brief_version)
        self.outbox.extend(events)
        summary = self.summaries.get(project.id)
        if summary is not None:
            self.summaries[project.id] = summary.model_copy(
                update={
                    "last_activity_at": project.updated_at,
                    "projection_version": summary.projection_version + 1,
                }
            )

    def list_brief_versions(
        self, organization_id: UUID, project_id: UUID
    ) -> tuple[BriefVersion, ...]:
        if self.get(organization_id, project_id) is None:
            return ()
        return tuple(self.briefs.get(project_id, ()))


def new_project_id() -> UUID:
    return new_uuid7()
