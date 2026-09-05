from __future__ import annotations

import threading

from .ports import SandboxBackend


class SandboxReaper:
    def __init__(self, backend: SandboxBackend, *, interval_seconds: float = 1.0) -> None:
        if not 0.25 <= interval_seconds <= 60:
            raise ValueError("SANDBOX_REAPER_INTERVAL_INVALID")
        self.backend = backend
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lumi-sandbox-reaper",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def __enter__(self) -> SandboxReaper:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.backend.reap_expired()
