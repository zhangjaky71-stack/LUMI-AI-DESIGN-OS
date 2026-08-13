from __future__ import annotations

import threading

from .models import TelemetryEvent


class MemoryCostTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryEvent] = []
        self._lock = threading.Lock()

    def record(self, event: TelemetryEvent) -> None:
        with self._lock:
            self.records.append(event)


class NullCostTelemetrySink:
    def record(self, event: TelemetryEvent) -> None:
        del event
