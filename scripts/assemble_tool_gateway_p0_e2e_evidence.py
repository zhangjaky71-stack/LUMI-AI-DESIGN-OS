#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from merge_tool_gateway_e2e_into_staging_evidence import merge
from validate_tool_gateway_e2e_evidence import (
    ToolGatewayE2EEvidenceError,
    validate_contract,
)

_SUCCESS = frozenset({"success", "succeeded", "ok", "completed"})
_ASSET_REF = re.compile(
    r"^asset://[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ARTIFACT_REF = re.compile(
    r"^artifact://[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_SENSITIVE_KEYS = frozenset(
    {
        "bucket",
        "object_key",
        "presigned_url",
        "signed_url",
        "download_url",
        "upload_url",
        "s3_url",
        "storage_url",
    }
)
_FORBIDDEN_SECRET_MARKERS = (
    "X-Subscription-Token",
    "x-subscription-token",
    "LUMI_BRAVE_SEARCH_API_KEY",
    "LUMI_TOOL_GATEWAY_AUTH_SECRET",
    "LUMI_TOOL_DATA_AUTH_SECRET",
    "LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET",
)


class AssembleError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssembleError(f"unable to read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise AssembleError(f"{label} must be a JSON object")
    return payload


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value == "PENDING" or "\x00" in value:
        raise AssembleError(f"{label} is required")
    return value


def _uuid(value: Any, label: str) -> str:
    text = _required_string(value, label)
    try:
        return str(UUID(text))
    except ValueError as exc:
        raise AssembleError(f"{label} must be a UUID") from exc


def _success(value: Any, label: str) -> None:
    if not isinstance(value, str) or value.strip().lower() not in _SUCCESS:
        raise AssembleError(f"{label} did not succeed: {value!r}")


def _input_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _contains_sensitive_storage(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower().replace("-", "_") in _SENSITIVE_KEYS:
                return True
            if _contains_sensitive_storage(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive_storage(child) for child in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "x-amz-signature=" in lowered or "amazonaws.com/" in lowered
    return False


def _secret_material_present(*payloads: dict[str, Any]) -> bool:
    serialized = "\n".join(json.dumps(item, sort_keys=True, default=str) for item in payloads)
    return any(marker in serialized for marker in _FORBIDDEN_SECRET_MARKERS)


def _call_entry(probe: dict[str, Any], tool: str) -> tuple[dict[str, Any], dict[str, Any]]:
    calls = probe.get("calls")
    if not isinstance(calls, dict):
        raise AssembleError("probe calls are missing")
    entry = calls.get(tool)
    if not isinstance(entry, dict):
        raise AssembleError(f"probe call is missing: {tool}")
    request = entry.get("request")
    result = entry.get("result")
    if not isinstance(request, dict) or not isinstance(result, dict):
        raise AssembleError(f"probe request/result is missing: {tool}")
    _uuid(request.get("tool_call_id"), f"probe.{tool}.tool_call_id")
    _required_string(request.get("trace_id"), f"probe.{tool}.trace_id")
    _success(result.get("status"), f"probe.{tool}.status")
    if result.get("resolved_version") != "1.0.0":
        raise AssembleError(f"probe.{tool}.resolved_version must be 1.0.0")
    resolved_name = result.get("resolved_name")
    if resolved_name not in {None, tool}:
        raise AssembleError(f"probe.{tool} resolved to unexpected tool: {resolved_name}")
    return request, result


def _first_ref(result: dict[str, Any], prefix: str, label: str) -> str:
    refs = result.get("resource_refs")
    if not isinstance(refs, list):
        raise AssembleError(f"{label} has no resource_refs")
    matches = [item for item in refs if isinstance(item, str) and item.startswith(prefix)]
    if len(matches) != 1:
        raise AssembleError(f"{label} must contain exactly one {prefix} resource ref")
    return matches[0]


def _audit_ids(db: dict[str, Any]) -> dict[str, str]:
    audit = db.get("audit")
    if not isinstance(audit, dict):
        raise AssembleError("DB audit evidence is missing")
    mapping = audit.get("event_ids_by_tool_call_id")
    if not isinstance(mapping, dict):
        raise AssembleError("DB audit event map is missing")
    result: dict[str, str] = {}
    for key, value in mapping.items():
        if isinstance(key, str) and isinstance(value, str) and value:
            result[key] = value
    return result


def _audit_event(mapping: dict[str, str], tool_call_id: str, label: str) -> str:
    value = mapping.get(tool_call_id)
    if not value:
        raise AssembleError(f"durable audit event is missing: {label}")
    return value


def _readiness(readiness: dict[str, Any], evidence_ref: str) -> dict[str, Any]:
    if readiness.get("http_status") != 200:
        raise AssembleError("Tool Gateway readiness HTTP status must be 200")
    response = readiness.get("response")
    if not isinstance(response, dict):
        raise AssembleError("Tool Gateway readiness response is missing")
    expected = {
        "service": "tool-gateway",
        "status": "ok",
        "adapter_count": 8,
        "runtime_binding_count": 4,
        "missing_adapters": [],
        "missing_runtime_bindings": [],
    }
    for key, value in expected.items():
        if response.get(key) != value:
            raise AssembleError(f"Tool Gateway readiness mismatch: {key}")
    return {
        "status": "PASS",
        "adapter_count": 8,
        "runtime_binding_count": 4,
        "missing_adapters": [],
        "missing_runtime_bindings": [],
        "probe_ref": evidence_ref,
    }


def _release_identity(staging: dict[str, Any]) -> dict[str, str]:
    release = staging.get("release_candidate")
    image_set = staging.get("container_image_set")
    if not isinstance(release, dict) or not isinstance(image_set, dict):
        raise AssembleError("parent staging release identity is incomplete")
    images = image_set.get("images")
    if not isinstance(images, dict):
        raise AssembleError("parent staging image set is missing")
    return {
        "git_sha": _required_string(release.get("git_sha"), "staging git_sha"),
        "version": _required_string(release.get("version"), "staging version"),
        "tool_gateway_image": _required_string(
            images.get("tool-gateway"),
            "staging Tool Gateway image",
        ),
        "agent_runtime_image": _required_string(
            images.get("agent-runtime"),
            "staging Agent Runtime image",
        ),
        "api_image": _required_string(images.get("api"), "staging API image"),
    }


def _data_policy(staging: dict[str, Any]) -> dict[str, bool]:
    policy = staging.get("data_policy")
    if not isinstance(policy, dict):
        raise AssembleError("parent staging data_policy is missing")
    if policy.get("production_customer_data_used") is not False:
        raise AssembleError("parent staging evidence must confirm no production customer data")
    if policy.get("test_data_only") is not True:
        raise AssembleError("parent staging evidence must confirm test_data_only=true")
    return {
        "synthetic_only": True,
        "production_customer_data_used": False,
        "secrets_recorded_in_evidence": False,
    }


def _call_common(
    probe: dict[str, Any],
    db: dict[str, Any],
    tool: str,
    audit_map: dict[str, str],
    evidence_ref: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request, result = _call_entry(probe, tool)
    call_id = _uuid(request.get("tool_call_id"), f"{tool}.tool_call_id")
    return (
        request,
        result,
        {
            "status": "PASS",
            "tool_call_id": call_id,
            "trace_id": _required_string(request.get("trace_id"), f"{tool}.trace_id"),
            "caller_service": "agent-runtime",
            "resolved_version": "1.0.0",
            "audit_event_id": _audit_event(audit_map, call_id, tool),
            "evidence_ref": evidence_ref,
        },
    )


def _sandbox_network_policy(data: dict[str, Any]) -> str:
    direct = data.get("network_policy")
    if isinstance(direct, str):
        return direct.lower()
    security = data.get("security")
    if isinstance(security, dict):
        nested = security.get("network_policy")
        if isinstance(nested, str):
            return nested.lower()
    raise AssembleError("sandbox result does not expose network_policy evidence")


def _assemble_calls(
    probe: dict[str, Any],
    db: dict[str, Any],
    probe_ref: str,
) -> dict[str, dict[str, Any]]:
    audit_map = _audit_ids(db)
    calls: dict[str, dict[str, Any]] = {}

    request, result, row = _call_common(probe, db, "web.search", audit_map, probe_ref)
    del request
    data = result.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not data["results"]:
        raise AssembleError("web.search did not return non-empty results")
    row.update(
        {
            "provider": "brave",
            "provider_host": "api.search.brave.com",
            "result_count": len(data["results"]),
        }
    )
    calls["web.search"] = row

    _, result, row = _call_common(probe, db, "web.fetch", audit_map, probe_ref)
    data = result.get("data")
    if not isinstance(data, dict):
        raise AssembleError("web.fetch inline data is missing")
    http_status = data.get("status")
    content_type = data.get("content_type")
    if not isinstance(http_status, int) or not isinstance(content_type, str):
        raise AssembleError("web.fetch status/content_type evidence is missing")
    row.update({"http_status": http_status, "content_type": content_type})
    calls["web.fetch"] = row

    _, result, row = _call_common(probe, db, "project.query", audit_map, probe_ref)
    data = result.get("data")
    if not isinstance(data, dict):
        raise AssembleError("project.query data is missing")
    row["project_id"] = _uuid(data.get("project_id"), "project.query project_id")
    calls["project.query"] = row

    for tool in ("asset.read", "media.inspect"):
        _, result, row = _call_common(probe, db, tool, audit_map, probe_ref)
        data = result.get("data")
        if not isinstance(data, dict):
            raise AssembleError(f"{tool} data is missing")
        ref = _first_ref(result, "asset://", tool)
        if not _ASSET_REF.fullmatch(ref):
            raise AssembleError(f"{tool} returned invalid asset ref")
        row.update(
            {
                "asset_ref": ref,
                "storage_location_exposed": _contains_sensitive_storage(data),
            }
        )
        if row["storage_location_exposed"]:
            raise AssembleError(f"{tool} exposes storage location")
        calls[tool] = row

    _, result, row = _call_common(probe, db, "artifact.query", audit_map, probe_ref)
    data = result.get("data")
    if not isinstance(data, dict):
        raise AssembleError("artifact.query data is missing")
    ref = _first_ref(result, "artifact://", "artifact.query")
    if not _ARTIFACT_REF.fullmatch(ref):
        raise AssembleError("artifact.query returned invalid artifact ref")
    row.update(
        {
            "artifact_ref": ref,
            "storage_location_exposed": _contains_sensitive_storage(data),
        }
    )
    if row["storage_location_exposed"]:
        raise AssembleError("artifact.query exposes storage location")
    calls["artifact.query"] = row

    request, result, row = _call_common(
        probe,
        db,
        "asset.write-derived",
        audit_map,
        probe_ref,
    )
    derived = db.get("derived_asset")
    idempotency = db.get("idempotency")
    rights = db.get("rights")
    if not all(isinstance(value, dict) for value in (derived, idempotency, rights)):
        raise AssembleError("derived write DB evidence is incomplete")
    assert isinstance(derived, dict)
    assert isinstance(idempotency, dict)
    assert isinstance(rights, dict)
    asset_ref = _first_ref(result, "asset://", "asset.write-derived")
    db_ref = _required_string(derived.get("derived_asset_ref"), "DB derived asset ref")
    if asset_ref != db_ref:
        raise AssembleError("derived write Tool Gateway ref differs from PostgreSQL Asset")
    arguments = request.get("arguments")
    if not isinstance(arguments, dict):
        raise AssembleError("derived write request arguments are missing")
    source_asset_id = _uuid(
        arguments.get("source_asset_id"),
        "asset.write-derived source_asset_id",
    )
    artifact_ref = _required_string(
        arguments.get("artifact_ref"),
        "asset.write-derived artifact_ref",
    )
    if not _ARTIFACT_REF.fullmatch(artifact_ref):
        raise AssembleError("derived write artifact_ref is not canonical")
    if rights.get("rights_inherited") is not True or rights.get("mismatched_fields") != []:
        raise AssembleError("derived AssetRights do not exactly inherit source rights")
    row.update(
        {
            "operation_id": _required_string(
                idempotency.get("operation_id"),
                "derived idempotency operation_id",
            ),
            "idempotency_key_hash": _required_string(
                idempotency.get("idempotency_key_hash"),
                "derived idempotency hash",
            ),
            "asset_ref": asset_ref,
            "source_asset_id": source_asset_id,
            "artifact_ref": artifact_ref,
            "rights_inherited": True,
        }
    )
    calls["asset.write-derived"] = row

    _, result, row = _call_common(probe, db, "sandbox.execute", audit_map, probe_ref)
    data = result.get("data")
    if not isinstance(data, dict):
        raise AssembleError("normal sandbox.execute data must remain inline")
    exit_code = data.get("exit_code")
    if exit_code != 0:
        raise AssembleError(f"normal sandbox.execute exit_code must be 0, got {exit_code!r}")
    row.update(
        {
            "exit_code": 0,
            "network_policy": _sandbox_network_policy(data),
        }
    )
    calls["sandbox.execute"] = row
    return calls


def _assemble_replay(
    probe: dict[str, Any],
    db: dict[str, Any],
    calls: dict[str, dict[str, Any]],
    db_ref: str,
) -> dict[str, Any]:
    replay = probe.get("idempotent_replay")
    idempotency = db.get("idempotency")
    derived = db.get("derived_asset")
    if not isinstance(replay, dict) or not isinstance(idempotency, dict) or not isinstance(derived, dict):
        raise AssembleError("replay evidence is incomplete")
    first_call = _uuid(replay.get("first_tool_call_id"), "replay first_tool_call_id")
    replay_call = _uuid(replay.get("replay_tool_call_id"), "replay replay_tool_call_id")
    if first_call != calls["asset.write-derived"]["tool_call_id"]:
        raise AssembleError("replay first call does not match derived write")
    first_ref = _required_string(replay.get("first_asset_ref"), "replay first_asset_ref")
    replay_ref = _required_string(replay.get("replay_asset_ref"), "replay replay_asset_ref")
    canonical_ref = calls["asset.write-derived"]["asset_ref"]
    if first_ref != canonical_ref or replay_ref != canonical_ref:
        raise AssembleError("replay did not return the canonical derived Asset")
    if replay.get("replayed") is not True or replay.get("same_asset_ref") is not True:
        raise AssembleError("derived write replay was not observed")
    if derived.get("adapter_invocation_count") != 1:
        raise AssembleError("derived write adapter invocation count must be 1")
    if derived.get("duplicate_derived_asset_count") != 0:
        raise AssembleError("derived write replay produced duplicate Asset rows")
    return {
        "status": "PASS",
        "tool": "asset.write-derived",
        "first_tool_call_id": first_call,
        "replay_tool_call_id": replay_call,
        "operation_id": calls["asset.write-derived"]["operation_id"],
        "idempotency_key_hash": calls["asset.write-derived"]["idempotency_key_hash"],
        "first_asset_ref": canonical_ref,
        "replay_asset_ref": canonical_ref,
        "replayed": True,
        "adapter_invocation_count": 1,
        "duplicate_derived_asset_count": 0,
        "evidence_ref": db_ref,
    }


def _assemble_offload(
    probe: dict[str, Any],
    s3: dict[str, Any],
    probe_ref: str,
    s3_ref: str,
) -> dict[str, Any]:
    offload = probe.get("result_offload")
    if not isinstance(offload, dict):
        raise AssembleError("probe result_offload is missing")
    call_id = _uuid(offload.get("tool_call_id"), "offload tool_call_id")
    result_ref = _required_string(offload.get("result_ref"), "probe offload result_ref")
    if offload.get("inline_data_present") is not False:
        raise AssembleError("oversized sandbox result must not remain inline")
    if s3.get("result_ref") != result_ref:
        raise AssembleError("S3 Head evidence result_ref differs from probe")
    if s3.get("object_head_verified") is not True:
        raise AssembleError("S3 HeadObject was not verified")
    if s3.get("metadata_sha256_verified") is not True:
        raise AssembleError("S3 sha256 metadata was not verified")
    if s3.get("public_url_returned") is not False:
        raise AssembleError("offloaded result exposed a public URL")
    content_length = s3.get("content_length")
    inline_limit = s3.get("inline_limit_bytes")
    if not isinstance(content_length, int) or not isinstance(inline_limit, int):
        raise AssembleError("S3 content length/inline limit evidence is invalid")
    if content_length <= inline_limit:
        raise AssembleError("S3 object does not exceed inline result limit")
    digest = _required_string(s3.get("sha256"), "S3 offload sha256")
    return {
        "status": "PASS",
        "tool": "sandbox.execute",
        "tool_call_id": call_id,
        "inline_limit_bytes": inline_limit,
        "serialized_result_bytes": content_length,
        "inline_data_present": False,
        "result_ref": result_ref,
        "sha256": digest,
        "object_head_verified": True,
        "public_url_returned": False,
        "evidence_ref": f"{probe_ref};{s3_ref}",
    }


def _assemble_audit(db: dict[str, Any], db_ref: str) -> dict[str, Any]:
    audit = db.get("audit")
    if not isinstance(audit, dict):
        raise AssembleError("DB durable audit evidence is missing")
    expected = audit.get("expected_call_count")
    persisted = audit.get("persisted_call_count")
    if not isinstance(expected, int) or expected < 10:
        raise AssembleError("durable audit expected_call_count must be >= 10")
    if persisted != expected:
        raise AssembleError("durable audit persisted count differs from expected")
    if audit.get("missing_tool_calls") != []:
        raise AssembleError("durable audit is missing Tool Gateway calls")
    if audit.get("cross_tenant_rows") != 0:
        raise AssembleError("durable audit contains cross-tenant rows")
    if audit.get("secret_material_present") is not False:
        raise AssembleError("durable audit contains secret material")
    return {
        "status": "PASS",
        "expected_call_count": expected,
        "persisted_call_count": persisted,
        "missing_tool_calls": [],
        "cross_tenant_rows": 0,
        "secret_material_present": False,
        "evidence_ref": db_ref,
    }


def _assemble_provider(
    search: dict[str, Any],
    calls: dict[str, dict[str, Any]],
    search_ref: str,
) -> dict[str, Any]:
    if search.get("provider") != "brave" or search.get("provider_host") != "api.search.brave.com":
        raise AssembleError("search evidence is not the canonical Brave provider")
    if search.get("live_request_observed") is not True:
        raise AssembleError("live Brave request was not established")
    if search.get("provider_http_status") != 200:
        raise AssembleError("Brave provider HTTP status must be 200")
    if search.get("redirect_followed") is not False:
        raise AssembleError("Brave provider redirect was followed")
    if search.get("credential_material_present") is not False:
        raise AssembleError("search evidence contains provider credential material")
    if search.get("tool_call_id") != calls["web.search"]["tool_call_id"]:
        raise AssembleError("search evidence tool_call_id differs from web.search probe")
    if search.get("result_count") != calls["web.search"]["result_count"]:
        raise AssembleError("search evidence result_count differs from web.search probe")
    return {
        "status": "PASS",
        "provider": "brave",
        "provider_host": "api.search.brave.com",
        "live_request_observed": True,
        "provider_http_status": 200,
        "result_count": calls["web.search"]["result_count"],
        "redirect_followed": False,
        "credential_material_present": False,
        "evidence_ref": search_ref,
        "observation_basis": search.get("observation_basis"),
        "direct_packet_capture": search.get("direct_packet_capture", False),
    }


def assemble(
    *,
    staging: dict[str, Any],
    probe: dict[str, Any],
    db: dict[str, Any],
    s3: dict[str, Any],
    readiness: dict[str, Any],
    search: dict[str, Any],
    refs: dict[str, str],
) -> dict[str, Any]:
    if probe.get("caller_service") != "agent-runtime":
        raise AssembleError("probe caller_service must be agent-runtime")
    if _secret_material_present(probe, db, s3, readiness, search):
        raise AssembleError("input evidence contains forbidden secret markers")

    calls = _assemble_calls(probe, db, refs["probe"])
    payload = {
        "schema_version": 1,
        "contract_id": "lumi-staging-tool-gateway-p0-e2e-v1",
        "environment": "staging",
        "release_identity": _release_identity(staging),
        "data_policy": _data_policy(staging),
        "readiness": _readiness(readiness, refs["readiness"]),
        "calls": calls,
        "idempotent_replay": _assemble_replay(
            probe,
            db,
            calls,
            refs["db"],
        ),
        "result_offload": _assemble_offload(
            probe,
            s3,
            refs["probe"],
            refs["s3"],
        ),
        "durable_audit": _assemble_audit(db, refs["db"]),
        "provider_search": _assemble_provider(search, calls, refs["search"]),
        "verdict": "PASS",
        "captured_at": datetime.now(UTC).isoformat(),
    }
    try:
        validate_contract(payload)
    except ToolGatewayE2EEvidenceError as exc:
        raise AssembleError(f"assembled Tool Gateway E2E contract is invalid: {exc}") from exc
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--s3", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--search", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merged-output", type=Path)
    args = parser.parse_args()

    inputs = {
        "staging": args.staging.resolve(),
        "probe": args.probe.resolve(),
        "db": args.db.resolve(),
        "s3": args.s3.resolve(),
        "readiness": args.readiness.resolve(),
        "search": args.search.resolve(),
    }
    output = args.output.resolve()
    if output in inputs.values():
        raise SystemExit("output must not overwrite an input evidence file")
    if args.merged_output is not None and args.merged_output.resolve() in {
        *inputs.values(),
        output,
    }:
        raise SystemExit("merged-output must be a new file")

    refs = {key: _input_ref(path) for key, path in inputs.items() if key != "staging"}
    try:
        staging = _load(inputs["staging"], "parent staging evidence")
        assembled = assemble(
            staging=staging,
            probe=_load(inputs["probe"], "Agent Runtime probe"),
            db=_load(inputs["db"], "PostgreSQL evidence"),
            s3=_load(inputs["s3"], "S3 evidence"),
            readiness=_load(inputs["readiness"], "readiness evidence"),
            search=_load(inputs["search"], "search evidence"),
            refs=refs,
        )
        _write(output, assembled)
        if args.merged_output is not None:
            merged = merge(staging, assembled)
            _write(args.merged_output.resolve(), merged)
    except AssembleError as exc:
        raise SystemExit(f"Tool Gateway P0 evidence assembly failed: {exc}") from exc

    print(output)
    if args.merged_output is not None:
        print(args.merged_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
