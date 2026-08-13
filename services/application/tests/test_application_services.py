from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lumi_application import (
    ApplicationContext,
    ApplicationInvariantViolation,
    IdempotencyClaim,
    IdempotencyClaimState,
    IdempotencyConflict,
    TransactionalExecutor,
    UseCaseResult,
    canonical_request_hash,
    claim_operation,
    require_access,
)
from lumi_domain import DomainEvent

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
OTHER_ORG_ID = UUID("01900000-0000-7000-8000-000000000002")
ACTOR_ID = UUID("01900000-0000-7000-8000-000000000003")
CORRELATION_ID = UUID("01900000-0000-7000-8000-000000000004")
AGGREGATE_ID = UUID("01900000-0000-7000-8000-000000000005")
EVENT_ID = UUID("01900000-0000-7000-8000-000000000006")


class FakeOutbox:
    def __init__(self, log: list[str]) -> None:
        self.events: list[DomainEvent] = []
        self.log = log

    async def append(self, event: DomainEvent) -> None:
        self.events.append(event)
        self.log.append(f"outbox:{event.name}")


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.projects = object()
        self.assets = object()
        self.artifacts = object()
        self.tasks = object()
        self.agent_runs = object()
        self.cost_ledger = object()
        self.outbox = FakeOutbox(self.log)
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
        self.log.append("enter")
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.log.append("exit")

    async def commit(self) -> None:
        self.commits += 1
        self.log.append("commit")

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.log.append("rollback")


class FakeFactory:
    def __init__(self) -> None:
        self.last: FakeUnitOfWork | None = None

    def __call__(self, context: ApplicationContext) -> FakeUnitOfWork:
        del context
        self.last = FakeUnitOfWork()
        return self.last


class FakeAuthorizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def require(
        self,
        context: ApplicationContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None:
        del context
        self.calls.append((action, resource_type, resource_id))


@dataclass
class FakeIdempotency:
    claim_value: IdempotencyClaim

    async def claim(
        self,
        context: ApplicationContext,
        *,
        key: str,
        operation_type: str,
        request_hash: str,
    ) -> IdempotencyClaim:
        del context, key, operation_type, request_hash
        return self.claim_value

    async def complete(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def fail(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


def context(*, organization_id: UUID = ORG_ID, actor_id: UUID | None = ACTOR_ID) -> ApplicationContext:
    return ApplicationContext(
        organization_id=organization_id,
        request_id="app-test",
        correlation_id=CORRELATION_ID,
        actor_id=actor_id,
    )


def event(*, organization_id: UUID = ORG_ID, event_id: UUID = EVENT_ID) -> DomainEvent:
    return DomainEvent(
        name="project.created",
        organization_id=organization_id,
        aggregate_id=AGGREGATE_ID,
        event_id=event_id,
        payload={"project_id": str(AGGREGATE_ID)},
    )


class ApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_appends_outbox_before_single_commit(self) -> None:
        factory = FakeFactory()
        executor = TransactionalExecutor(factory)  # type: ignore[arg-type]

        async def handler(app_context: ApplicationContext, command: str, uow: Any) -> UseCaseResult[str]:
            del app_context, uow
            return UseCaseResult(value=command.upper(), events=(event(),))

        result = await executor.execute(context(), "ok", handler)
        self.assertEqual(result, "OK")
        assert factory.last is not None
        self.assertEqual(factory.last.commits, 1)
        self.assertEqual(factory.last.rollbacks, 0)
        self.assertEqual(factory.last.log, ["enter", "outbox:project.created", "commit", "exit"])

    async def test_handler_failure_rolls_back_and_preserves_exception(self) -> None:
        factory = FakeFactory()
        executor = TransactionalExecutor(factory)  # type: ignore[arg-type]

        async def handler(app_context: ApplicationContext, command: str, uow: Any) -> UseCaseResult[str]:
            del app_context, command, uow
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            await executor.execute(context(), "ignored", handler)
        assert factory.last is not None
        self.assertEqual(factory.last.commits, 0)
        self.assertEqual(factory.last.rollbacks, 1)

    async def test_cancellation_rolls_back_and_is_not_swallowed(self) -> None:
        factory = FakeFactory()
        executor = TransactionalExecutor(factory)  # type: ignore[arg-type]

        async def handler(app_context: ApplicationContext, command: str, uow: Any) -> UseCaseResult[str]:
            del app_context, command, uow
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await executor.execute(context(), "ignored", handler)
        assert factory.last is not None
        self.assertEqual(factory.last.commits, 0)
        self.assertEqual(factory.last.rollbacks, 1)

    async def test_cross_tenant_event_is_rejected_before_commit(self) -> None:
        factory = FakeFactory()
        executor = TransactionalExecutor(factory)  # type: ignore[arg-type]

        async def handler(app_context: ApplicationContext, command: str, uow: Any) -> UseCaseResult[str]:
            del app_context, uow
            return UseCaseResult(value=command, events=(event(organization_id=OTHER_ORG_ID),))

        with self.assertRaises(ApplicationInvariantViolation):
            await executor.execute(context(), "x", handler)
        assert factory.last is not None
        self.assertEqual(factory.last.commits, 0)
        self.assertEqual(factory.last.rollbacks, 1)

    async def test_duplicate_event_id_in_one_result_is_rejected(self) -> None:
        factory = FakeFactory()
        executor = TransactionalExecutor(factory)  # type: ignore[arg-type]

        async def handler(app_context: ApplicationContext, command: str, uow: Any) -> UseCaseResult[str]:
            del app_context, uow
            return UseCaseResult(value=command, events=(event(), event()))

        with self.assertRaisesRegex(ApplicationInvariantViolation, "duplicate domain event ID"):
            await executor.execute(context(), "x", handler)
        assert factory.last is not None
        self.assertEqual(factory.last.commits, 0)
        self.assertEqual(factory.last.rollbacks, 1)

    async def test_authorization_requires_authenticated_actor_before_port_call(self) -> None:
        authorizer = FakeAuthorizer()
        with self.assertRaises(PermissionError):
            await require_access(
                authorizer,
                context(actor_id=None),
                action="project.read",
                resource_type="project",
            )
        self.assertEqual(authorizer.calls, [])

        await require_access(
            authorizer,
            context(),
            action="project.read",
            resource_type="project",
            resource_id=str(AGGREGATE_ID),
        )
        self.assertEqual(
            authorizer.calls,
            [("project.read", "project", str(AGGREGATE_ID))],
        )

    async def test_idempotency_conflict_is_transport_agnostic_application_error(self) -> None:
        port = FakeIdempotency(IdempotencyClaim(IdempotencyClaimState.CONFLICT))
        with self.assertRaises(IdempotencyConflict):
            await claim_operation(
                port,
                context(),
                key="operation-123",
                operation_type="project.create",
                request_hash="a" * 64,
            )

    async def test_request_hash_is_canonical_and_rejects_nan(self) -> None:
        left = canonical_request_hash({"b": [2, 1], "a": {"x": "y"}})
        right = canonical_request_hash({"a": {"x": "y"}, "b": [2, 1]})
        self.assertEqual(left, right)
        with self.assertRaises(ValueError):
            canonical_request_hash({"bad": float("nan")})


if __name__ == "__main__":
    unittest.main()
