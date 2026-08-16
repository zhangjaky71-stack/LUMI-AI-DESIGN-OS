from __future__ import annotations

import json
from pathlib import Path

from lumi_api.artifacts.gc import GcCandidate
from lumi_api.artifacts.models import (
    Artifact,
    ArtifactBranch,
    ArtifactVersion,
    LineageEdge,
    ProvenanceManifest,
    ProvenanceRecord,
    RightsPolicy,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports" / "nodes" / "NODE-15" / "generated-schemas"

SCHEMAS = {
    "artifact-v1.schema.json": Artifact.model_json_schema(),
    "artifact-branch-v1.schema.json": ArtifactBranch.model_json_schema(),
    "artifact-version-v1.schema.json": ArtifactVersion.model_json_schema(),
    "lineage-edge-v1.schema.json": LineageEdge.model_json_schema(),
    "provenance-v1.schema.json": ProvenanceRecord.model_json_schema(),
    "rights-v1.schema.json": RightsPolicy.model_json_schema(),
    "export-provenance-manifest-v1.schema.json": ProvenanceManifest.model_json_schema(),
    "gc-candidate-v1.schema.json": GcCandidate.model_json_schema(),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, schema in SCHEMAS.items():
        path = OUTPUT / name
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
