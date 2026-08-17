from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .models import DesignDocument, OperationExecution


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    operation_ids: tuple[str, ...]
    before: DesignDocument
    after: DesignDocument


class CommandHistory:
    def __init__(self) -> None:
        self._entries: list[HistoryEntry] = []
        self._cursor = 0

    def push(self, before: DesignDocument, execution: OperationExecution) -> None:
        self._entries = self._entries[: self._cursor]
        self._entries.append(
            HistoryEntry(
                execution.applied_operation_ids,
                deepcopy(before),
                deepcopy(execution.document),
            )
        )
        self._cursor = len(self._entries)

    def undo(self, current: DesignDocument) -> DesignDocument:
        if self._cursor == 0:
            return deepcopy(current)
        self._cursor -= 1
        return deepcopy(self._entries[self._cursor].before)

    def redo(self, current: DesignDocument) -> DesignDocument:
        if self._cursor >= len(self._entries):
            return deepcopy(current)
        result = deepcopy(self._entries[self._cursor].after)
        self._cursor += 1
        return result

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def cursor(self) -> int:
        return self._cursor
