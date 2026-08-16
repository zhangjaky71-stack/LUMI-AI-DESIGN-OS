# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

from lumi_worker_media.app import submit_job
from lumi_worker_media.event_runtime import DeadLetterReplayService, KombuDomainPublisher
from lumi_worker_media.job_dlq import (
    JobDeadLetterReplayService,
    PostgresJobReplayState,
)
from lumi_worker_media.postgres_runtime import PostgresDeadLetterStore
from lumi_worker_media.queue_contracts import JobKind, JobMessage


class CelerySubmitter:
    def submit(self, kind: JobKind, message: JobMessage) -> None:
        submit_job(kind, message)


async def run(organization_id: UUID, record_id: UUID) -> None:
    dsn = os.environ["LUMI_DATABASE_APP_URL"]
    broker = os.environ["RABBITMQ_URL"]
    store = PostgresDeadLetterStore(dsn)
    record = await store.get(organization_id, record_id)
    if record is None:
        raise ValueError("DEAD_LETTER_NOT_FOUND")
    if record.message_kind == "domain_event":
        service = DeadLetterReplayService(
            store=store,
            publisher=KombuDomainPublisher(broker),
        )
        replayed = await service.replay(organization_id, record_id)
    elif record.message_kind == "job":
        service = JobDeadLetterReplayService(
            store=store,
            state=PostgresJobReplayState(dsn),
            submitter=CelerySubmitter(),
        )
        replayed = await service.replay(organization_id, record_id)
    else:
        raise ValueError("DEAD_LETTER_KIND_UNSUPPORTED")
    print(
        f"replayed {replayed.id} message={replayed.message_id} "
        f"at={replayed.replayed_at}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay one tenant-scoped NODE-19 DLQ record"
    )
    parser.add_argument("organization_id", type=UUID)
    parser.add_argument("record_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(run(args.organization_id, args.record_id))


if __name__ == "__main__":
    main()
