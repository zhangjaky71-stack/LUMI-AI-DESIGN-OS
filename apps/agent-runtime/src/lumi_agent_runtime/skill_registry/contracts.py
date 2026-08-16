from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID

from lumi_agent_runtime.deep_runtime.contracts import MaterializedSkill

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_.-]{0,255}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_MEMORY_SCOPE = re.compile(r"^(project|brand|user|organization)(:[A-Za-z0-9_.-]+)?$")
_MAX_FILE_CHARS = 512_000
_MAX_PACKAGE_CHARS = 2_000_000


class SkillEvalStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SkillScope:
    organization_id: UUID | None = None
    project_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.project_id is not None and self.organization_id is None:
            raise ValueError("SKILL_REGISTRY_PROJECT_SCOPE_REQUIRES_ORG")

    @classmethod
    def global_scope(cls) -> "SkillScope":
        return cls()

    @classmethod
    def organization(cls, organization_id: UUID) -> "SkillScope":
        return cls(organization_id=organization_id)

    @classmethod
    def project(cls, organization_id: UUID, project_id: UUID) -> "SkillScope":
        return cls(organization_id=organization_id, project_id=project_id)

    @property
    def key(self) -> str:
        if self.project_id is not None:
            return f"project:{self.organization_id}:{self.project_id}"
        if self.organization_id is not None:
            return f"organization:{self.organization_id}"
        return "global"

    def visible_chain(self) -> tuple["SkillScope", ...]:
        if self.project_id is not None:
            return (
                self,
                SkillScope.organization(self.organization_id),
                SkillScope.global_scope(),
            )
        if self.organization_id is not None:
            return (self, SkillScope.global_scope())
        return (self,)


@dataclass(frozen=True, slots=True)
class SkillFile:
    path: str
    content: str

    def __post_init__(self) -> None:
        validate_package_path(self.path)
        if len(self.content) > _MAX_FILE_CHARS:
            raise ValueError("SKILL_REGISTRY_FILE_TOO_LARGE")


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    version: str
    description: str
    files: tuple[SkillFile, ...]
    dependency_refs: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_skill_id(self.skill_id)
        validate_version(self.version)
        if not self.description or len(self.description) > 2_000:
            raise ValueError("SKILL_REGISTRY_DESCRIPTION_INVALID")
        if not self.files:
            raise ValueError("SKILL_REGISTRY_FILES_REQUIRED")
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("SKILL_REGISTRY_FILE_DUPLICATE")
        if "SKILL.md" not in paths:
            raise ValueError("SKILL_REGISTRY_SKILL_MD_REQUIRED")
        if sum(len(item.content) for item in self.files) > _MAX_PACKAGE_CHARS:
            raise ValueError("SKILL_REGISTRY_PACKAGE_TOO_LARGE")
        if len(self.dependency_refs) != len(set(self.dependency_refs)):
            raise ValueError("SKILL_REGISTRY_DEPENDENCY_DUPLICATE")
        for ref in self.dependency_refs:
            parse_skill_ref(ref)
        if len(self.required_tools) != len(set(self.required_tools)):
            raise ValueError("SKILL_REGISTRY_TOOL_DUPLICATE")
        for tool in self.required_tools:
            if not _TOOL.fullmatch(tool):
                raise ValueError(f"SKILL_REGISTRY_TOOL_INVALID:{tool}")
        if len(self.required_permissions) != len(set(self.required_permissions)):
            raise ValueError("SKILL_REGISTRY_PERMISSION_DUPLICATE")
        for permission in self.required_permissions:
            validate_required_permission(permission)
        MaterializedSkill(
            skill_id=self.skill_id,
            exact_version=self.version,
            path=f"/skills/{self.skill_id}/{self.version}/SKILL.md",
            content_hash="0" * 64,
            required_tools=self.required_tools,
            required_permissions=self.required_permissions,
        )

    @property
    def identity(self) -> str:
        return f"{self.skill_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class SkillEvaluationEvidence:
    policy_id: str
    suite_id: str
    status: SkillEvalStatus
    score: str
    subject_hash: str
    evidence_ref: str
    evaluated_at: str

    def __post_init__(self) -> None:
        if not self.policy_id or len(self.policy_id) > 128:
            raise ValueError("SKILL_REGISTRY_EVAL_POLICY_INVALID")
        if not self.suite_id or len(self.suite_id) > 128:
            raise ValueError("SKILL_REGISTRY_EVAL_SUITE_INVALID")
        try:
            score = Decimal(self.score)
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("SKILL_REGISTRY_EVAL_SCORE_INVALID") from exc
        if not score.is_finite() or not Decimal("0") <= score <= Decimal("1"):
            raise ValueError("SKILL_REGISTRY_EVAL_SCORE_INVALID")
        if not _HASH.fullmatch(self.subject_hash):
            raise ValueError("SKILL_REGISTRY_EVAL_SUBJECT_HASH_INVALID")
        if not _REF.fullmatch(self.evidence_ref):
            raise ValueError("SKILL_REGISTRY_EVAL_REF_INVALID")
        if not self.evaluated_at or len(self.evaluated_at) > 64:
            raise ValueError("SKILL_REGISTRY_EVAL_TIME_INVALID")


@dataclass(frozen=True, slots=True)
class PublishedSkill:
    scope: SkillScope
    manifest: SkillManifest
    dependency_hashes: tuple[tuple[str, str], ...]
    content_hash: str
    provenance_ref: str
    evaluation: SkillEvaluationEvidence
    published_by: str
    published_at: str

    def __post_init__(self) -> None:
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("SKILL_REGISTRY_CONTENT_HASH_INVALID")
        if not _REF.fullmatch(self.provenance_ref):
            raise ValueError("SKILL_REGISTRY_PROVENANCE_REF_INVALID")
        refs = tuple(item[0] for item in self.dependency_hashes)
        if refs != self.manifest.dependency_refs:
            raise ValueError("SKILL_REGISTRY_DEPENDENCY_HASH_ORDER_INVALID")
        for ref, digest in self.dependency_hashes:
            parse_skill_ref(ref)
            if not _HASH.fullmatch(digest):
                raise ValueError("SKILL_REGISTRY_DEPENDENCY_HASH_INVALID")

    @property
    def identity(self) -> str:
        return self.manifest.identity


def validate_skill_id(value: str) -> None:
    if not _NAME.fullmatch(value):
        raise ValueError("SKILL_REGISTRY_SKILL_ID_INVALID")


def validate_version(value: str) -> None:
    if not _VERSION.fullmatch(value):
        raise ValueError("SKILL_REGISTRY_VERSION_INVALID")


def parse_skill_ref(value: str) -> tuple[str, str]:
    if value.count("@") != 1:
        raise ValueError("SKILL_REGISTRY_REF_INVALID")
    skill_id, version = value.split("@", 1)
    try:
        validate_skill_id(skill_id)
        validate_version(version)
    except ValueError as exc:
        raise ValueError("SKILL_REGISTRY_REF_INVALID") from exc
    return skill_id, version


def validate_package_path(value: str) -> None:
    if not value or len(value) > 512 or value.startswith(("/", "\\")):
        raise ValueError("SKILL_REGISTRY_FILE_PATH_INVALID")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("SKILL_REGISTRY_FILE_PATH_INVALID")
    if parts[0] == ".lumi":
        raise ValueError("SKILL_REGISTRY_RESERVED_PATH")


def validate_required_permission(value: str) -> None:
    if value == "sandbox.execute":
        return
    for prefix in ("memory.read:", "memory.write:"):
        if value.startswith(prefix):
            scope = value.removeprefix(prefix)
            if _MEMORY_SCOPE.fullmatch(scope):
                return
    raise ValueError(f"SKILL_REGISTRY_PERMISSION_INVALID:{value}")


def scope_to_dict(scope: SkillScope) -> dict[str, str | None]:
    return {
        "organization_id": str(scope.organization_id) if scope.organization_id else None,
        "project_id": str(scope.project_id) if scope.project_id else None,
    }


def scope_from_dict(value: dict[str, Any]) -> SkillScope:
    organization = value.get("organization_id")
    project = value.get("project_id")
    return SkillScope(
        organization_id=UUID(organization) if organization else None,
        project_id=UUID(project) if project else None,
    )


def file_to_dict(value: SkillFile) -> dict[str, str]:
    return {"path": value.path, "content": value.content}


def file_from_dict(value: dict[str, Any]) -> SkillFile:
    return SkillFile(path=value["path"], content=value["content"])


def manifest_to_dict(value: SkillManifest) -> dict[str, Any]:
    return {
        "skill_id": value.skill_id,
        "version": value.version,
        "description": value.description,
        "files": [file_to_dict(item) for item in value.files],
        "dependency_refs": list(value.dependency_refs),
        "required_tools": list(value.required_tools),
        "required_permissions": list(value.required_permissions),
    }


def manifest_from_dict(value: dict[str, Any]) -> SkillManifest:
    return SkillManifest(
        skill_id=value["skill_id"],
        version=value["version"],
        description=value["description"],
        files=tuple(file_from_dict(item) for item in value["files"]),
        dependency_refs=tuple(value.get("dependency_refs", ())),
        required_tools=tuple(value.get("required_tools", ())),
        required_permissions=tuple(value.get("required_permissions", ())),
    )


def evaluation_to_dict(value: SkillEvaluationEvidence) -> dict[str, str]:
    return {
        "policy_id": value.policy_id,
        "suite_id": value.suite_id,
        "status": value.status.value,
        "score": value.score,
        "subject_hash": value.subject_hash,
        "evidence_ref": value.evidence_ref,
        "evaluated_at": value.evaluated_at,
    }


def evaluation_from_dict(value: dict[str, Any]) -> SkillEvaluationEvidence:
    return SkillEvaluationEvidence(
        policy_id=value["policy_id"],
        suite_id=value["suite_id"],
        status=SkillEvalStatus(value["status"]),
        score=value["score"],
        subject_hash=value["subject_hash"],
        evidence_ref=value["evidence_ref"],
        evaluated_at=value["evaluated_at"],
    )


def published_to_dict(value: PublishedSkill) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": scope_to_dict(value.scope),
        "manifest": manifest_to_dict(value.manifest),
        "dependency_hashes": [
            {"ref": ref, "content_hash": digest}
            for ref, digest in value.dependency_hashes
        ],
        "content_hash": value.content_hash,
        "provenance_ref": value.provenance_ref,
        "evaluation": evaluation_to_dict(value.evaluation),
        "published_by": value.published_by,
        "published_at": value.published_at,
    }


def published_from_dict(value: dict[str, Any]) -> PublishedSkill:
    return PublishedSkill(
        scope=scope_from_dict(value["scope"]),
        manifest=manifest_from_dict(value["manifest"]),
        dependency_hashes=tuple(
            (item["ref"], item["content_hash"])
            for item in value.get("dependency_hashes", ())
        ),
        content_hash=value["content_hash"],
        provenance_ref=value["provenance_ref"],
        evaluation=evaluation_from_dict(value["evaluation"]),
        published_by=value["published_by"],
        published_at=value["published_at"],
    )
