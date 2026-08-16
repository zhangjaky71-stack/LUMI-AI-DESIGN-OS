from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from .models import ArtifactVersion, LineageEdge, ProvenanceManifest, RightsPolicy


def _source_closure(
    root_version_id: UUID,
    versions: tuple[ArtifactVersion, ...],
    edges: tuple[LineageEdge, ...],
) -> tuple[ArtifactVersion, ...]:
    version_by_id = {item.id: item for item in versions}
    adjacency: dict[UUID, set[UUID]] = {}
    for edge in edges:
        adjacency.setdefault(edge.artifact_version_id, set()).add(
            edge.source_artifact_version_id
        )

    found: set[UUID] = set()
    stack = list(adjacency.get(root_version_id, set()))
    while stack:
        version_id = stack.pop()
        if version_id in found:
            continue
        version = version_by_id.get(version_id)
        if version is None:
            raise ValueError("lineage source is missing from manifest version set")
        found.add(version_id)
        stack.extend(adjacency.get(version_id, set()))
    return tuple(version_by_id[item] for item in sorted(found, key=str))


def _dedupe_rights(rights: tuple[RightsPolicy, ...]) -> tuple[RightsPolicy, ...]:
    seen: set[str] = set()
    result: list[RightsPolicy] = []
    for policy in rights:
        key = json.dumps(
            policy.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if key not in seen:
            seen.add(key)
            result.append(policy)
    return tuple(result)


def build_provenance_manifest(
    root: ArtifactVersion,
    versions: tuple[ArtifactVersion, ...],
    edges: tuple[LineageEdge, ...],
    *,
    created_at: datetime,
) -> ProvenanceManifest:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("manifest created_at must be timezone-aware")
    version_by_id = {item.id: item for item in versions}
    if root.id not in version_by_id:
        raise ValueError("root version must be present in manifest version set")
    sources = _source_closure(root.id, versions, edges)
    all_versions = (root, *sources)

    source_assets: set[UUID] = set()
    models: set[tuple[str, str]] = set()
    checksums: set[str] = set()
    rights: list[RightsPolicy] = []
    for version in all_versions:
        source_assets.update(version.provenance.input_asset_ids)
        if version.provenance.provider and version.provenance.model:
            models.add((version.provenance.provider, version.provenance.model))
        checksums.update(file.checksum_sha256 for file in version.files)
        rights.append(version.rights)

    return ProvenanceManifest(
        artifact_version_id=root.id,
        created_at=created_at,
        source_artifact_version_ids=tuple(item.id for item in sources),
        source_asset_ids=tuple(sorted(source_assets, key=str)),
        models=tuple(sorted(models)),
        rights=_dedupe_rights(tuple(rights)),
        checksums=tuple(sorted(checksums)),
        code_git_sha=root.provenance.code_git_sha,
        constraint_snapshot_hash=root.constraint_snapshot_hash,
    )


def canonical_manifest_json(manifest: ProvenanceManifest) -> str:
    return json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def manifest_hash_sha256(manifest: ProvenanceManifest) -> str:
    return hashlib.sha256(canonical_manifest_json(manifest).encode("utf-8")).hexdigest()
