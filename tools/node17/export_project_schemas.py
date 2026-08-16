from __future__ import annotations

import json
from pathlib import Path

from lumi_api.projects import (
    BriefVersion,
    ProjectAuditEntry,
    ProjectBrief,
    ProjectEvent,
    ProjectListQuery,
    ProjectRecord,
    ProjectSettings,
    ProjectSummary,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "nodes" / "NODE-17" / "generated-schemas"

SCHEMAS = {
    "project-brief-v1.schema.json": ProjectBrief,
    "project-settings-v1.schema.json": ProjectSettings,
    "project-record-v1.schema.json": ProjectRecord,
    "project-brief-version-v1.schema.json": BriefVersion,
    "project-summary-v1.schema.json": ProjectSummary,
    "project-event-v1.schema.json": ProjectEvent,
    "project-audit-entry-v1.schema.json": ProjectAuditEntry,
    "project-list-query-v1.schema.json": ProjectListQuery,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        path = OUT / name
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
