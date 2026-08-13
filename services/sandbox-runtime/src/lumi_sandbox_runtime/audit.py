from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import SandboxAuditRecord


class MemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[SandboxAuditRecord] = []
        self._lock = threading.Lock()

    def emit(self, record: SandboxAuditRecord) -> None:
        with self._lock:
            self.records.append(record)


class JsonlAuditSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, record: SandboxAuditRecord) -> None:
        payload = asdict(record)
        encoded = json.dumps(payload, ensure_ascii=False, default=_json_default, sort_keys=True)
        with self._lock:
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, encoded.encode("utf-8") + b"\n")
            finally:
                os.close(descriptor)


def _json_default(value: Any) -> str:
    return str(value)
