from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import SandboxAuditRecord

_DEFAULT_AUDIT_BYTES = 16 * 1024 * 1024


class MemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[SandboxAuditRecord] = []
        self._lock = threading.Lock()

    def emit(self, record: SandboxAuditRecord) -> None:
        with self._lock:
            self.records.append(record)


class JsonlAuditSink:
    """Bounded local reference sink; production should use the platform audit pipeline."""

    def __init__(self, path: Path, *, max_bytes: int = _DEFAULT_AUDIT_BYTES) -> None:
        if not 1024 <= max_bytes <= 1024 * 1024 * 1024:
            raise ValueError("SANDBOX_AUDIT_LIMIT_INVALID")
        self.path = path
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, record: SandboxAuditRecord) -> None:
        payload = asdict(record)
        encoded = json.dumps(payload, ensure_ascii=False, default=_json_default, sort_keys=True)
        line = encoded.encode("utf-8") + b"\n"
        with self._lock:
            self._rotate_if_needed(len(line))
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, line)
            finally:
                os.close(descriptor)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current = self.path.stat().st_size
        except FileNotFoundError:
            current = 0
        if current == 0 or current + incoming_bytes <= self.max_bytes:
            return
        rotated = self.path.with_name(self.path.name + ".1")
        rotated.unlink(missing_ok=True)
        os.replace(self.path, rotated)
        try:
            rotated.chmod(0o600)
        except OSError:
            pass


def _json_default(value: Any) -> str:
    return str(value)
