from __future__ import annotations

from pathlib import Path
from typing import Literal, overload

from .dependencies import (
    StaticNamedCatalog,
    StaticVersionedCatalog,
    load_bootstrap_catalog as _load_bootstrap_catalog,
)
from .errors import AgentDependencyError


@overload
def load_bootstrap_catalog(
    path: Path,
    section: Literal["skills"],
) -> StaticVersionedCatalog: ...


@overload
def load_bootstrap_catalog(
    path: Path,
    section: Literal[
        "context_policies",
        "budget_policies",
        "output_schemas",
        "eval_profiles",
    ],
) -> StaticNamedCatalog: ...


def load_bootstrap_catalog(
    path: Path,
    section: str,
) -> StaticNamedCatalog | StaticVersionedCatalog:
    catalog = _load_bootstrap_catalog(path, section)
    if section == "skills":
        if not isinstance(catalog, StaticVersionedCatalog):
            raise AgentDependencyError("bootstrap skills must be versioned")
        return catalog
    if not isinstance(catalog, StaticNamedCatalog):
        raise AgentDependencyError(
            f"bootstrap named catalog has wrong type: {section}"
        )
    return catalog


def load_skill_catalog(path: Path) -> StaticVersionedCatalog:
    return load_bootstrap_catalog(path, "skills")


def load_named_catalog(path: Path, section: str) -> StaticNamedCatalog:
    if section == "skills":
        raise AgentDependencyError("skills require load_skill_catalog")
    catalog = _load_bootstrap_catalog(path, section)
    if not isinstance(catalog, StaticNamedCatalog):
        raise AgentDependencyError(
            f"bootstrap named catalog has wrong type: {section}"
        )
    return catalog
