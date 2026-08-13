from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lumi_agent_runtime.agent_registry.dependencies import (
    CatalogEntry,
    StaticNamedCatalog,
)

from .errors import SkillDefinitionInvalidError


def load_skill_schema_catalog(path: Path) -> StaticNamedCatalog:
    payload = _read(path)
    if payload.get("schema") != "lumi.skill-io-registry.v1":
        raise SkillDefinitionInvalidError("Skill schema registry version invalid")
    return StaticNamedCatalog(
        _entries(
            payload.get("schemas"),
            source_root=path.parents[2],
        )
    )


def load_skill_eval_catalog(path: Path) -> StaticNamedCatalog:
    payload = _read(path)
    if payload.get("schema") != "lumi.skill-eval-profile-registry.v1":
        raise SkillDefinitionInvalidError("Skill eval registry version invalid")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise SkillDefinitionInvalidError("Skill eval profiles must be an object")
    rows: dict[str, CatalogEntry] = {}
    for key, raw in profiles.items():
        if not isinstance(raw, dict):
            raise SkillDefinitionInvalidError(f"Skill eval profile invalid: {key}")
        version = raw.get("version")
        if not isinstance(version, str) or not version:
            raise SkillDefinitionInvalidError(
                f"Skill eval profile version invalid: {key}"
            )
        rows[str(key)] = CatalogEntry(
            key=str(key),
            exact_version=version,
            content_hash=_hash_json(raw),
            source_ref=f"{path.as_posix()}#{key}",
        )
    return StaticNamedCatalog(rows)


def _entries(
    value: Any,
    *,
    source_root: Path,
) -> dict[str, CatalogEntry]:
    if not isinstance(value, dict):
        raise SkillDefinitionInvalidError("Skill schema rows must be an object")
    rows: dict[str, CatalogEntry] = {}
    for key, raw in value.items():
        if not isinstance(raw, dict):
            raise SkillDefinitionInvalidError(f"Skill schema entry invalid: {key}")
        version = raw.get("version")
        source_ref = raw.get("source_ref")
        if not isinstance(version, str) or not version:
            raise SkillDefinitionInvalidError(
                f"Skill schema version invalid: {key}"
            )
        if not isinstance(source_ref, str) or not source_ref:
            raise SkillDefinitionInvalidError(
                f"Skill schema source missing: {key}"
            )
        source_path = source_root / source_ref
        if not source_path.is_file():
            raise SkillDefinitionInvalidError(
                f"Skill schema source not found: {source_ref}"
            )
        schema_payload = _read(source_path)
        rows[str(key)] = CatalogEntry(
            key=str(key),
            exact_version=version,
            content_hash=_hash_json(schema_payload),
            source_ref=source_ref,
        )
    return rows


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillDefinitionInvalidError(f"invalid JSON registry: {path}") from exc
    if not isinstance(payload, dict):
        raise SkillDefinitionInvalidError(f"JSON registry must be an object: {path}")
    return payload


def _hash_json(value: Any) -> str:
    import hashlib

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
