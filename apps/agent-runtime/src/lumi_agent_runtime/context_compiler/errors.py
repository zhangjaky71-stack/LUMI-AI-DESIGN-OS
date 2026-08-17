from __future__ import annotations

from dataclasses import dataclass


class ContextCompilerError(RuntimeError):
    """Base error for NODE-32 deterministic context compilation."""


class ContextSourceValidationError(ContextCompilerError):
    pass


class ContextSourcePermissionError(ContextCompilerError):
    pass


class ContextBundleIntegrityError(ContextCompilerError):
    pass


class ContextBundleNotFoundError(ContextCompilerError):
    pass


@dataclass(frozen=True, slots=True)
class ContextConflict:
    key: str
    channel: str
    source_type: str
    source_refs: tuple[str, ...]
    fingerprints: tuple[str, ...]
    constraint_ids: tuple[str, ...] = ()


class ContextConflictError(ContextCompilerError):
    def __init__(self, conflicts: tuple[ContextConflict, ...]) -> None:
        self.conflicts = conflicts
        joined = ";".join(
            f"{item.channel}:{item.key}:{item.source_type}:"
            f"{','.join(item.source_refs)}"
            for item in conflicts
        )
        super().__init__(f"CONTEXT_SAME_LEVEL_CONFLICT:{joined}")
