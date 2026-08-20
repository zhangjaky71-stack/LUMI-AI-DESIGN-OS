#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "staging/acceptance/api-provenance-sources-v1.json"
TEMPLATE = ROOT / "staging/acceptance/evidence-template.json"
CONTRACT_MODULES = {
    "node71-validator": ROOT / "scripts/validate_staging_acceptance_contract.py",
    "node71-gate": ROOT / "scripts/staging-acceptance-gate.py",
    "video-producer": ROOT / "scripts/validate_video_generation_producer_binding.py",
    "side-effect": ROOT / "scripts/validate_side_effect_control_provenance.py",
    "audit": ROOT / "scripts/validate_tool_audit_provenance.py",
    "approval": ROOT / "scripts/validate_tool_approval_provenance.py",
    "tool-data": ROOT / "scripts/validate_tool_data_provenance.py",
}


class ApiProvenanceSourceManifestError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiProvenanceSourceManifestError(f"unable to read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ApiProvenanceSourceManifestError(f"JSON root must be an object: {path}")
    return value


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"lumi_{name.replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        raise ApiProvenanceSourceManifestError(f"unable to load contract module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module_required_sources(name: str, module: ModuleType) -> set[str]:
    candidates = (
        "API_REQUIRED_SOURCES",
        "API_REQUIRED_SOURCE_PATHS",
        "REQUIRED_API_SOURCES",
    )
    for attribute in candidates:
        raw = getattr(module, attribute, None)
        if raw is None:
            continue
        if not isinstance(raw, (list, set, frozenset, tuple)) or not all(
            isinstance(item, str) and item for item in raw
        ):
            raise ApiProvenanceSourceManifestError(
                f"{name}.{attribute} must be a collection of non-empty strings"
            )
        return set(raw)
    raise ApiProvenanceSourceManifestError(
        f"{name} exposes no canonical API required-source collection"
    )


def validate() -> None:
    manifest = _load_json(MANIFEST)
    if manifest.get("schema_version") != 1 or manifest.get("service") != "api":
        raise ApiProvenanceSourceManifestError("API provenance source manifest identity is invalid")
    raw_sources = manifest.get("required_source_paths")
    if not isinstance(raw_sources, list) or not raw_sources or not all(
        isinstance(item, str) and item for item in raw_sources
    ):
        raise ApiProvenanceSourceManifestError(
            "required_source_paths must be a non-empty string array"
        )
    if len(raw_sources) != len(set(raw_sources)):
        raise ApiProvenanceSourceManifestError("required_source_paths contains duplicates")
    manifest_sources = set(raw_sources)
    for relative in raw_sources:
        if not (ROOT / relative).exists():
            raise ApiProvenanceSourceManifestError(
                f"canonical API provenance source is missing: {relative}"
            )

    union: set[str] = set()
    loaded: dict[str, ModuleType] = {}
    for name, path in CONTRACT_MODULES.items():
        module = _load_module(name, path)
        loaded[name] = module
        module_sources = _module_required_sources(name, module)
        missing = sorted(module_sources - manifest_sources)
        if missing:
            raise ApiProvenanceSourceManifestError(
                f"{name} requires API sources absent from canonical manifest: "
                + ", ".join(missing)
            )
        union.update(module_sources)

    if union != manifest_sources:
        unclaimed = sorted(manifest_sources - union)
        raise ApiProvenanceSourceManifestError(
            "canonical API provenance manifest contains sources not claimed by any release contract: "
            + ", ".join(unclaimed)
        )

    template = _load_json(TEMPLATE)
    try:
        template_sources = template["container_image_set"]["provenance"]["api"]["source_paths"]
    except (KeyError, TypeError) as exc:
        raise ApiProvenanceSourceManifestError(
            "staging evidence template API source_paths is missing"
        ) from exc
    if not isinstance(template_sources, list) or set(template_sources) != manifest_sources:
        raise ApiProvenanceSourceManifestError(
            "staging evidence template API source_paths must exactly match canonical manifest"
        )
    if len(template_sources) != len(manifest_sources):
        raise ApiProvenanceSourceManifestError(
            "staging evidence template API source_paths contains duplicates"
        )

    video_producer = loaded.get("video-producer")
    if video_producer is None or not callable(getattr(video_producer, "main", None)):
        raise ApiProvenanceSourceManifestError("video producer release contract is not executable")
    video_producer.main()


def main() -> int:
    validate()
    print("Canonical API provenance source manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
