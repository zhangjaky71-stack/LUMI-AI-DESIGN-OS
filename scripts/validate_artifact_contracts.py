from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/artifacts/v1"
SOURCE = ROOT / "services/artifact-history/src/lumi_artifacts"
EXPECTED_SCHEMA_IDS = {
    "artifact-history.schema.json": "https://schemas.lumi.dev/artifacts/v1/artifact-history.schema.json",
    "provenance.schema.json": "https://schemas.lumi.dev/artifacts/v1/provenance.schema.json",
    "rights.schema.json": "https://schemas.lumi.dev/artifacts/v1/rights.schema.json",
    "export-provenance-manifest.schema.json": "https://schemas.lumi.dev/artifacts/v1/export-provenance-manifest.schema.json",
}
FORBIDDEN_IMPORTS = ("fastapi","sqlalchemy","alembic","langchain","langgraph","openai","anthropic","boto3","httpx","requests","celery","pika")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def validate_json_contracts() -> None:
    manifest = load(CONTRACT / "manifest.json")
    assert manifest["schema_version"] == "1.0"
    assert len(manifest["artifact_types"]) == 9
    assert "CANVAS" not in manifest["artifact_types"]
    assert manifest["version_statuses"] == ["DRAFT", "READY", "APPROVED", "REJECTED", "ARCHIVED"]
    assert len(manifest["lineage_edge_types"]) == 7
    assert manifest["content_hash_algorithm"] == "SHA-256"
    assert manifest["design_document_hash_source"] == "LUMI_CANONICAL_JSON_V1"

    for filename, expected_id in EXPECTED_SCHEMA_IDS.items():
        schema = load(CONTRACT / filename)
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", filename
        assert schema.get("$id") == expected_id, filename

    history = load(CONTRACT / "artifact-history.schema.json")
    version = history["$defs"]["version"]["properties"]
    assert version["status"]["enum"] == manifest["version_statuses"]
    assert version["content_hash"]["$ref"] == "#/$defs/sha256"
    assert version["constraint_snapshot_hash"]["$ref"] == "#/$defs/sha256"
    assert history["$defs"]["edge"]["properties"]["type"]["enum"] == manifest["lineage_edge_types"]

    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in CONTRACT.glob("*.json")
    )
    for forbidden in ("presigned_url", "secret_key", "api_key", "raw_prompt", "password"):
        assert forbidden not in text, f"forbidden sensitive/ephemeral field in artifact contract: {forbidden}"

    fixture = load(CONTRACT / "fixtures/lineage.json")
    assert fixture["fixture_version"] == "1.0"
    assert len(fixture["versions"]) >= 4
    assert len(fixture["edges"]) >= 3
    edge_pairs = {(edge["from_version_id"], edge["to_version_id"]) for edge in fixture["edges"]}
    assert ("v2", "v4") in edge_pairs, "restore lineage fixture missing"
    assert sum(1 for edge in fixture["edges"] if edge["to_version_id"] == "v4") >= 2, (
        "fixture must demonstrate multi-parent lineage"
    )


def validate_reference_boundary() -> None:
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(FORBIDDEN_IMPORTS):
                    raise AssertionError(f"forbidden dependency {name} in {path.relative_to(ROOT)}")
                if name.startswith("lumi_") and not name.startswith("lumi_artifacts"):
                    raise AssertionError(f"Artifact V1 reference runtime must remain self-contained: {name}")


def main() -> None:
    validate_json_contracts()
    validate_reference_boundary()
    print("Artifact V1 contracts OK: history, lineage, provenance, rights, export and boundary validated")


if __name__ == "__main__":
    main()
