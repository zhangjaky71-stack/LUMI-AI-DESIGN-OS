from __future__ import annotations

import json
from pathlib import Path

from lumi_api.idempotency.models import (
    IdempotencyOperation,
    OperationRequest,
    ProviderReconciliation,
    SideEffectOutcome,
)

OUT = Path("reports/nodes/NODE-20/generated-schemas")
SCHEMAS = {
    "idempotency-operation-v1.schema.json": IdempotencyOperation,
    "operation-request-v1.schema.json": OperationRequest,
    "provider-reconciliation-v1.schema.json": ProviderReconciliation,
    "side-effect-outcome-v1.schema.json": SideEffectOutcome,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = OUT / filename
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
