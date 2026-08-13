from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from lumi_domain import DomainEvent

from .context import ApplicationContext
from .errors import ApplicationInvariantViolation
from .ports import ApplicationUnitOfWork, UnitOfWorkFactory

CommandT = TypeVar("CommandT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class UseCaseResult(Generic[ResultT]):
    value: ResultT
    events: tuple[DomainEvent, ...] = field(default_factory=tuple)


UseCaseHandler = Callable[
    [ApplicationContext, CommandT, ApplicationUnitOfWork],
    Awaitable[UseCaseResult[ResultT]],
]


class TransactionalExecutor:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        context: ApplicationContext,
        command: CommandT,
        handler: UseCaseHandler[CommandT, ResultT],
    ) -> ResultT:
        unit_of_work = self._uow_factory(context)
        async with unit_of_work:
            try:
                result = await handler(context, command, unit_of_work)
                await self._append_events(context, unit_of_work, result.events)
                await unit_of_work.commit()
                return result.value
            except BaseException:
                await unit_of_work.rollback()
                raise

    @staticmethod
    async def _append_events(
        context: ApplicationContext,
        unit_of_work: ApplicationUnitOfWork,
        events: tuple[DomainEvent, ...],
    ) -> None:
        seen_ids = set()
        for event in events:
            if event.organization_id != context.organization_id:
                raise ApplicationInvariantViolation(
                    "domain event organization does not match application context"
                )
            if event.event_id in seen_ids:
                raise ApplicationInvariantViolation(
                    f"duplicate domain event ID in one use-case result: {event.event_id}"
                )
            seen_ids.add(event.event_id)
            await unit_of_work.outbox.append(event)
