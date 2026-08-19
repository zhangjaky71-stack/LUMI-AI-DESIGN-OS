from __future__ import annotations

import os

from .app import celery_app
from .queue_contracts import QUEUE_BY_JOB_KIND

_DEFAULT_CONCURRENCY = 4
_MAX_CONCURRENCY = 32
_ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def worker_argv() -> list[str]:
    concurrency = _bounded_int_env(
        "LUMI_WORKER_MEDIA_CONCURRENCY",
        default=_DEFAULT_CONCURRENCY,
        minimum=1,
        maximum=_MAX_CONCURRENCY,
    )
    log_level = os.getenv("LUMI_WORKER_MEDIA_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _ALLOWED_LOG_LEVELS:
        raise RuntimeError("LUMI_WORKER_MEDIA_LOG_LEVEL_INVALID")

    queues = ",".join(dict.fromkeys(QUEUE_BY_JOB_KIND.values()))
    if not queues:
        raise RuntimeError("WORKER_MEDIA_QUEUE_SET_EMPTY")

    return [
        "worker",
        f"--loglevel={log_level}",
        f"--concurrency={concurrency}",
        f"--queues={queues}",
        "--hostname=worker-media@%h",
    ]


def main() -> None:
    celery_app.worker_main(worker_argv())


def _bounded_int_env(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}_INVALID") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name}_OUT_OF_RANGE")
    return value


if __name__ == "__main__":
    main()
