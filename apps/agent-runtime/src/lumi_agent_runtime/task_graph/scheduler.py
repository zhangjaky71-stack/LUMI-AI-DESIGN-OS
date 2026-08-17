from __future__ import annotations

from ._scheduler_claims import _SchedulerClaimsMixin
from ._scheduler_core import _SchedulerCoreMixin
from ._scheduler_finalize import _SchedulerFinalizeMixin
from ._scheduler_internal import _SchedulerInternalMixin
from ._scheduler_waits import _SchedulerWaitsMixin
from .store import TaskGraphStore


class TaskGraphScheduler(
    _SchedulerCoreMixin,
    _SchedulerClaimsMixin,
    _SchedulerWaitsMixin,
    _SchedulerInternalMixin,
    _SchedulerFinalizeMixin,
):
    """Recoverable DAG scheduler with CAS, lease fencing, retries, budget and control semantics."""

    def __init__(self, store: TaskGraphStore) -> None:
        self.store = store


__all__ = ["TaskGraphScheduler"]
