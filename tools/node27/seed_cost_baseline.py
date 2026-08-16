from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from uuid import UUID

ORG_A = UUID("00000000-0000-7000-8000-000000002701")
ORG_B = UUID("00000000-0000-7000-8000-000000002702")
OP_BASELINE = UUID("00000000-0000-7000-8000-000000002711")
COST_BASELINE = UUID("00000000-0000-7000-8000-000000002721")


async def seed(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            for org_id, slug in ((ORG_A, "node27-a"), (ORG_B, "node27-b")):
                await connection.execute(
                    """
                    INSERT INTO organizations (id, name, slug)
                    VALUES ($1,$2,$3) ON CONFLICT (id) DO NOTHING
                    """,
                    org_id,
                    slug,
                    slug,
                )
            await connection.execute(
                """
                INSERT INTO idempotency_operations (
                    id, organization_id, idempotency_key, operation_type,
                    request_hash, status, side_effect_kind, compensation_mode, paid
                ) VALUES ($1,$2,'node27-baseline','model.invoke',$3,'in_progress',
                          'paid_model_invocation','non_compensatable',true)
                ON CONFLICT (id) DO NOTHING
                """,
                OP_BASELINE,
                ORG_A,
                "a" * 64,
            )
            await connection.execute(
                """
                INSERT INTO cost_ledger (
                    id, organization_id, operation_id, provider, model,
                    entry_type, amount, currency, occurred_at, metadata_json
                ) VALUES ($1,$2,$3,'fixture','legacy-model','charge',$4,'USD',now(),
                          '{"node27":"baseline"}'::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                COST_BASELINE,
                ORG_A,
                OP_BASELINE,
                Decimal("0.12500000"),
            )
    finally:
        await connection.close()
    print("NODE-27 baseline seed: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    asyncio.run(seed(args.dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
