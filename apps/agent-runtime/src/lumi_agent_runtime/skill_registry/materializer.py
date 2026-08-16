from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import SkillRegistryMaterializationError


@dataclass(frozen=True, slots=True)
class MaterializationFile:
    path: str
    content: str

    def __post_init__(self) -> None:
        _validate_materialization_path(self.path)


class SkillPackageSink(Protocol):
    async def install(
        self,
        *,
        skill_id: str,
        exact_version: str,
        content_hash: str,
        files: tuple[MaterializationFile, ...],
    ) -> None: ...


class InMemorySkillPackageSink:
    def __init__(self) -> None:
        self.installed: dict[tuple[str, str], tuple[str, dict[str, str]]] = {}

    async def install(
        self,
        *,
        skill_id: str,
        exact_version: str,
        content_hash: str,
        files: tuple[MaterializationFile, ...],
    ) -> None:
        key = (skill_id, exact_version)
        payload = {item.path: item.content for item in files}
        existing = self.installed.get(key)
        if existing is not None and existing[0] != content_hash:
            raise SkillRegistryMaterializationError(
                "SKILL_REGISTRY_MATERIALIZED_HASH_CONFLICT"
            )
        self.installed[key] = (content_hash, payload)


class AtomicDirectorySkillPackageSink:
    """Writes package trees below a host staging root without symlinks."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = asyncio.Lock()

    async def install(
        self,
        *,
        skill_id: str,
        exact_version: str,
        content_hash: str,
        files: tuple[MaterializationFile, ...],
    ) -> None:
        target = self._root / skill_id / exact_version
        marker = target / ".lumi" / "content-hash"
        async with self._lock:
            if target.exists():
                if marker.exists() and marker.read_text(encoding="utf-8").strip() == content_hash:
                    return
                raise SkillRegistryMaterializationError(
                    "SKILL_REGISTRY_MATERIALIZED_HASH_CONFLICT"
                )
            tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            if tmp.exists():
                shutil.rmtree(tmp)
            try:
                tmp.mkdir(parents=True, exist_ok=False)
                for item in files:
                    path = tmp.joinpath(*item.path.split("/"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(item.content, encoding="utf-8", newline="\n")
                lumi = tmp / ".lumi"
                lumi.mkdir(parents=True, exist_ok=True)
                (lumi / "content-hash").write_text(content_hash + "\n", encoding="utf-8")
                os.replace(tmp, target)
            except Exception:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
                raise


def dependency_index(entries: tuple[tuple[str, str], ...]) -> str:
    return json.dumps(
        [
            {"ref": ref, "content_hash": digest}
            for ref, digest in entries
        ],
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"


def _validate_materialization_path(value: str) -> None:
    if not value or len(value) > 1024 or value.startswith(("/", "\\")):
        raise ValueError("SKILL_REGISTRY_MATERIALIZATION_PATH_INVALID")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("SKILL_REGISTRY_MATERIALIZATION_PATH_INVALID")
