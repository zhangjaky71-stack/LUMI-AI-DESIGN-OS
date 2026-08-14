from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .history import ArtifactHistory, ArtifactHistoryError


class BranchHeadConflict(ArtifactHistoryError):
    pass


@dataclass(frozen=True, slots=True)
class CompilerProvenance:
    compiler_version: str
    document_id: str
    schema_version: str
    document_version: int
    resource_versions: Mapping[str, str]
    font_versions: Mapping[str, str]
    compile_hash: str


def next_version_number(history: ArtifactHistory, artifact_id: str) -> int:
    return max(
        (version.version_number for version in history.versions.values() if version.artifact_id == artifact_id),
        default=0,
    ) + 1


def advance_branch_head_cas(
    history: ArtifactHistory,
    *,
    branch_id: str,
    expected_head_version_id: str | None,
    next_head_version_id: str,
) -> None:
    branch = history.branches.get(branch_id)
    version = history.versions.get(next_head_version_id)
    if branch is None or version is None:
        raise ArtifactHistoryError("branch/version missing")
    if version.artifact_id != branch.artifact_id or version.organization_id != branch.organization_id:
        raise ArtifactHistoryError("branch head must belong to branch artifact/tenant")
    if branch.head_version_id != expected_head_version_id:
        raise BranchHeadConflict("branch head compare-and-swap conflict")
    history.branches[branch_id] = replace(branch, head_version_id=next_head_version_id)


def compiler_provenance_payload(value: CompilerProvenance) -> dict[str, object]:
    if len(value.compile_hash) != 64 or any(ch not in "0123456789abcdef" for ch in value.compile_hash):
        raise ValueError("compile_hash must be lowercase SHA-256")
    return {
        "compiler_version": value.compiler_version,
        "document_id": value.document_id,
        "schema_version": value.schema_version,
        "document_version": value.document_version,
        "resource_versions": dict(sorted(value.resource_versions.items())),
        "font_versions": dict(sorted(value.font_versions.items())),
        "compile_hash": value.compile_hash,
    }
