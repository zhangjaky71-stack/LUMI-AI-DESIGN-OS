#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOL_GATEWAY_SOURCES = frozenset(
    {
        "services/tool-gateway/Dockerfile",
        "services/tool-gateway/pyproject.toml",
        "services/tool-gateway/src/lumi_tool_gateway/service.py",
        "services/tool-gateway/src/lumi_tool_gateway/result_offload.py",
        "services/asset-storage/src/lumi_asset_storage/s3.py",
    }
)
APP_FILES = (
    ROOT / "infra/iac/environments/staging/app/main.tf",
    ROOT / "infra/iac/environments/production/app/main.tf",
)
STORAGE_MODULE = ROOT / "infra/iac/modules/storage/main.tf"
COMPUTE_MODULE = ROOT / "infra/iac/modules/compute/main.tf"


class ToolResultOffloadProvenanceError(RuntimeError):
    pass


def validate_evidence(payload: dict[str, Any]) -> None:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise ToolResultOffloadProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise ToolResultOffloadProvenanceError("container_image_set.provenance is missing")
    tool_gateway = provenance.get("tool-gateway")
    if not isinstance(tool_gateway, dict):
        raise ToolResultOffloadProvenanceError("tool-gateway image provenance is missing")
    source_paths = tool_gateway.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise ToolResultOffloadProvenanceError(
            "tool-gateway image provenance source_paths is invalid"
        )
    missing = sorted(REQUIRED_TOOL_GATEWAY_SOURCES - set(source_paths))
    if missing:
        raise ToolResultOffloadProvenanceError(
            "tool-gateway image provenance is missing durable result-offload sources: "
            + ", ".join(missing)
        )


def validate_source_chain() -> None:
    for relative in REQUIRED_TOOL_GATEWAY_SOURCES:
        if not (ROOT / relative).is_file():
            raise ToolResultOffloadProvenanceError(
                f"required durable result-offload source is missing: {relative}"
            )

    dockerfile = (ROOT / "services/tool-gateway/Dockerfile").read_text(encoding="utf-8")
    for fragment in (
        "COPY . /workspace",
        "uv sync --all-packages --frozen --no-dev",
        'USER 10001:10001',
    ):
        if fragment not in dockerfile:
            raise ToolResultOffloadProvenanceError(
                f"Tool Gateway image closure is missing boundary: {fragment}"
            )

    pyproject = (ROOT / "services/tool-gateway/pyproject.toml").read_text(encoding="utf-8")
    if '"lumi-asset-storage[s3]"' not in pyproject:
        raise ToolResultOffloadProvenanceError(
            "Tool Gateway must reuse canonical lumi-asset-storage[s3]"
        )

    offloader = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/result_offload.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "class S3ResultOffloader",
        "S3ObjectStore(",
        'os.getenv("LUMI_TOOL_RESULT_BUCKET"',
        'os.getenv("LUMI_S3_REGION"',
        'object_key = f"tool-results/v1/',
        'return f"s3ref://',
        'head.metadata.get("sha256") != digest',
    ):
        if fragment not in offloader:
            raise ToolResultOffloadProvenanceError(
                f"durable result offloader is missing boundary: {fragment}"
            )
    for forbidden in (
        "generate_presigned_url",
        "file://",
        "tempfile",
        "NamedTemporaryFile",
    ):
        if forbidden in offloader:
            raise ToolResultOffloadProvenanceError(
                f"durable result offloader contains forbidden fallback: {forbidden}"
            )

    service = (
        ROOT / "services/tool-gateway/src/lumi_tool_gateway/service.py"
    ).read_text(encoding="utf-8")
    for fragment in (
        "S3ResultOffloader.from_env()",
        "result_offloader=result_offloader",
        '"result-offloader"',
    ):
        if fragment not in service:
            raise ToolResultOffloadProvenanceError(
                f"Hosted Tool Gateway is missing result-offload binding: {fragment}"
            )

    for path in APP_FILES:
        source = path.read_text(encoding="utf-8")
        block = _terraform_service_block(source, "tool-gateway")
        for fragment in (
            'LUMI_TOOL_RESULT_BUCKET = local.bucket_names["exports"]',
            "LUMI_S3_REGION          = var.region",
            's3_bucket_arns         = [local.bucket_arns["exports"]]',
        ):
            if fragment not in block:
                raise ToolResultOffloadProvenanceError(
                    f"{path.relative_to(ROOT)} missing least-privilege offload wiring: {fragment}"
                )
        if 'local.bucket_arns["assets"]' in block or 'local.bucket_arns["sandbox"]' in block:
            raise ToolResultOffloadProvenanceError(
                f"{path.relative_to(ROOT)} grants Tool Gateway non-exports bucket access"
            )

    storage = STORAGE_MODULE.read_text(encoding="utf-8")
    for fragment in (
        'block_public_acls       = true',
        'block_public_policy     = true',
        'restrict_public_buckets = true',
        'object_ownership = "BucketOwnerEnforced"',
        'sse_algorithm     = "aws:kms"',
        'bucket_key_enabled = true',
        'variable = "aws:SecureTransport"',
        'each.key == "exports"',
        'id     = "expire-exports"',
    ):
        if fragment not in storage:
            raise ToolResultOffloadProvenanceError(
                f"storage module is missing result-offload boundary: {fragment}"
            )

    compute = COMPUTE_MODULE.read_text(encoding="utf-8")
    for fragment in (
        "services_with_s3",
        '"s3:PutObject"',
        '"kms:Encrypt"',
        'resources = each.value.s3_bucket_arns',
    ):
        if fragment not in compute:
            raise ToolResultOffloadProvenanceError(
                f"compute module is missing declared-bucket IAM boundary: {fragment}"
            )


def _terraform_service_block(source: str, service_name: str) -> str:
    marker = f"    {service_name} = {{"
    start = source.find(marker)
    if start < 0:
        raise ToolResultOffloadProvenanceError(
            f"Terraform service block is missing: {service_name}"
        )
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ToolResultOffloadProvenanceError(
        f"Terraform service block is unterminated: {service_name}"
    )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolResultOffloadProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolResultOffloadProvenanceError("evidence must be a JSON object")
    return payload


def self_test() -> None:
    validate_source_chain()
    clean = {
        "container_image_set": {
            "provenance": {
                "tool-gateway": {
                    "source_paths": sorted(REQUIRED_TOOL_GATEWAY_SOURCES),
                }
            }
        }
    }
    validate_evidence(clean)
    broken = json.loads(json.dumps(clean))
    broken["container_image_set"]["provenance"]["tool-gateway"]["source_paths"].remove(
        "services/tool-gateway/src/lumi_tool_gateway/result_offload.py"
    )
    try:
        validate_evidence(broken)
    except ToolResultOffloadProvenanceError:
        pass
    else:
        raise ToolResultOffloadProvenanceError(
            "self-test accepted missing durable result-offload source"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.evidence is not None:
        validate_source_chain()
        validate_evidence(_load(args.evidence))
    if not args.self_test and args.evidence is None:
        parser.error("one of --self-test or --evidence is required")
    print("Tool Gateway durable result offload provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
