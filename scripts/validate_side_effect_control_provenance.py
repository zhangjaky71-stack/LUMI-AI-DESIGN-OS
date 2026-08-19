#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGING_WORKFLOW = ROOT / ".github" / "workflows" / "staging-acceptance-gate.yml"
PUBLIC_ALB_DENY = ROOT / "infra" / "iac" / "modules" / "platform-app" / "internal-path-deny.tf"
REQUIRED_API_SOURCES = frozenset(
    {
        "apps/api/src/lumi_api/product_app.py",
        "apps/api/src/lumi_api/tool_side_effect_control.py",
        "apps/api/src/lumi_api/idempotency/gateway.py",
    }
)


class SideEffectProvenanceError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SideEffectProvenanceError(f"unable to read evidence JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SideEffectProvenanceError("evidence must be a JSON object")
    return payload


def validate_evidence(payload: dict[str, Any]) -> None:
    image_set = payload.get("container_image_set")
    if not isinstance(image_set, dict):
        raise SideEffectProvenanceError("container_image_set is missing")
    provenance = image_set.get("provenance")
    if not isinstance(provenance, dict):
        raise SideEffectProvenanceError("container_image_set.provenance is missing")
    api = provenance.get("api")
    if not isinstance(api, dict):
        raise SideEffectProvenanceError("api image provenance is missing")
    source_paths = api.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) and item for item in source_paths
    ):
        raise SideEffectProvenanceError("api image provenance source_paths is invalid")
    missing = sorted(REQUIRED_API_SOURCES - set(source_paths))
    if missing:
        raise SideEffectProvenanceError(
            "api image provenance is missing canonical Tool Gateway side-effect sources: "
            + ", ".join(missing)
        )


def validate_source_chain() -> None:
    for relative in REQUIRED_API_SOURCES:
        if not (ROOT / relative).is_file():
            raise SideEffectProvenanceError(f"required API source is missing: {relative}")

    control_source = (ROOT / "apps/api/src/lumi_api/tool_side_effect_control.py").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'frozenset({"tool-gateway"})',
        "SideEffectGateway(database_url)",
        "mark_provider_attempt_started",
        "mark_ambiguous",
        "hmac.compare_digest",
    ):
        if fragment not in control_source:
            raise SideEffectProvenanceError(
                f"private side-effect control source is missing boundary: {fragment}"
            )

    if not PUBLIC_ALB_DENY.is_file():
        raise SideEffectProvenanceError("public ALB internal-path denial contract is missing")
    alb_source = PUBLIC_ALB_DENY.read_text(encoding="utf-8")
    for fragment in (
        'priority     = 1',
        'type = "fixed-response"',
        'status_code  = "404"',
        'values = ["/internal", "/internal/*"]',
    ):
        if fragment not in alb_source:
            raise SideEffectProvenanceError(
                f"public ALB internal-path denial is missing boundary: {fragment}"
            )

    workflow = STAGING_WORKFLOW.read_text(encoding="utf-8")
    for fragment in (
        "python3 scripts/validate_side_effect_control_provenance.py",
        '--evidence "$LUMI_STAGING_EVIDENCE_PATH"',
    ):
        if fragment not in workflow:
            raise SideEffectProvenanceError(
                "Staging Acceptance must validate side-effect-control image provenance "
                "against the submitted evidence"
            )


def self_test() -> None:
    clean = {
        "container_image_set": {
            "provenance": {
                "api": {"source_paths": sorted(REQUIRED_API_SOURCES)},
            }
        }
    }
    validate_evidence(clean)

    missing = json.loads(json.dumps(clean))
    missing["container_image_set"]["provenance"]["api"]["source_paths"].remove(
        "apps/api/src/lumi_api/tool_side_effect_control.py"
    )
    try:
        validate_evidence(missing)
    except SideEffectProvenanceError:
        pass
    else:
        raise SideEffectProvenanceError("self-test accepted missing side-effect control source")

    validate_source_chain()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.evidence is not None:
        validate_evidence(_load_object(args.evidence))
    if not args.self_test and args.evidence is None:
        parser.error("one of --self-test or --evidence is required")
    print("Tool Gateway side-effect provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
