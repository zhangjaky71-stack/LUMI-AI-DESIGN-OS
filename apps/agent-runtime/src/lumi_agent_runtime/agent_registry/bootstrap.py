from __future__ import annotations

from pathlib import Path

from .dependencies import (
    StaticNamedCatalog,
    StaticVersionedCatalog,
    load_bootstrap_catalog,
)
from .errors import AgentDependencyError


def load_skill_catalog(path: Path) -> StaticVersionedCatalog:
    catalog = load_bootstrap_catalog(path, "skills")
    if not isinstance(catalog, StaticVersionedCatalog):
        raise AgentDependencyError("bootstrap skills must be versioned")
    return catalog


def load_named_catalog(path: Path, section: str) -> StaticNamedCatalog:
    if section == "skills":
        raise AgentDependencyError("skills require load_skill_catalog")
    catalog = load_bootstrap_catalog(path, section)
    if not isinstance(catalog, StaticNamedCatalog):
        raise AgentDependencyError(
            f"bootstrap named catalog has wrong type: {section}"
        )
    return catalog
