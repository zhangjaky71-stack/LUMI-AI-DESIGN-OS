from __future__ import annotations

from copy import deepcopy

from .canonical import canonicalize
from .models import DesignDocument, IrIssue, IrRuntimeError
from .validate import parse_document


def _record(document: DesignDocument, source: str, target: str) -> DesignDocument:
    result = deepcopy(document)
    provenance = result.setdefault("metadata", {}).get("migration_provenance")
    history = list(provenance) if isinstance(provenance, list) else []
    history.append(
        {
            "from": source,
            "to": target,
            "source_canonical": canonicalize(document),
        }
    )
    result["metadata"]["migration_provenance"] = history
    result["schema_version"] = target
    return result


MIGRATIONS = {
    "1.0": ("1.1", lambda document: _record(document, "1.0", "1.1")),
    "1.1": ("2.0", lambda document: _record(document, "1.1", "2.0")),
}


def migrate(document: DesignDocument, target_version: str) -> DesignDocument:
    current = parse_document(document)
    seen: set[str] = set()
    while current["schema_version"] != target_version:
        source = current["schema_version"]
        if source in seen or source not in MIGRATIONS:
            raise IrRuntimeError(
                IrIssue(
                    "IR_VERSION_UNSUPPORTED",
                    f"no migration path from {source} to {target_version}",
                )
            )
        seen.add(source)
        _, step = MIGRATIONS[source]
        current = parse_document(step(current))
    return current
