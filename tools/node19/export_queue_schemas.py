from __future__ import annotations

import json
from pathlib import Path

from lumi_api.events.envelope import EventEnvelope
from lumi_api.events.payloads import AssetReadyV1, ProjectCreatedV1
from lumi_api.queueing import JobScheduleRequest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "nodes" / "NODE-19" / "generated-schemas"

SCHEMAS = {
    "job-schedule-request-v1.schema.json": JobScheduleRequest,
    "project-created-envelope-v1.schema.json": EventEnvelope[ProjectCreatedV1],
    "asset-ready-envelope-v1.schema.json": EventEnvelope[AssetReadyV1],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        (OUT / name).write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(OUT / name)


if __name__ == "__main__":
    main()
