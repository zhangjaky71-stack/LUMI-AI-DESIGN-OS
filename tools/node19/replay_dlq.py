# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

from lumi_worker_media.event_runtime import DeadLetterReplayService, KombuDomainPublisher
from lumi_worker_media.postgres_runtime import PostgresDeadLetterStore


async def run(organization_id: UUID, record_id: UUID) -> None:
    dsn = os.environ["LUMI_DATABASE_APP_URL"]
    broker = os.environ["RABBITMQ_URL"]
    service = DeadLetterReplayService(
        store=PostgresDeadLetterStore(dsn),
        publisher=KombuDomainPublisher(broker),
    )
    record = await service.replay(organization_id, record_id)
    print(f"replayed {record.id} message={record.message_id} at={record.replayed_at}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay one tenant-scoped NODE-19 DLQ record")
    parser.add_argument("organization_id", type=UUID)
    parser.add_argument("record_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(run(args.organization_id, args.record_id))


if __name__ == "__main__":
    main()
