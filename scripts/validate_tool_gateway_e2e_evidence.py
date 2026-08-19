#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "staging/acceptance/tool-gateway-e2e-v1.json"
REQUIRED_TOOLS = frozenset(
    {
        "web.search",
        "web.fetch",
        "project.query",
        "asset.read",
        "artifact.query",
        "media.inspect",
        "asset.write-derived",
        "sandbox.execute",
    }
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_ASSET_REF = re.compile(
    r"^asset://[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ARTIFACT_REF = re.compile(
    r"^artifact://[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_S3_REF = re.compile(r"^s3ref://[^\s#]+#sha256=([0-9a-f]{64})$")


class ToolGatewayE2EEvidenceError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ToolGatewayE2EEvidenceError(message)


def _string(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty")
    text = str(value)
    _require(text != "PENDING", f"{label} is still PENDING")
    _require("\x00" not in text, f"{label} contains NUL")
    return text


def _uuid(value: Any, label: str) -> str:
    text = _string(value, label)
    try:
        UUID(text)
    except ValueError as exc:
        raise ToolGatewayE2EEvidenceError(f"{label} must be a UUID") from exc
    return text


def _bool(value: Any, expected: bool, label: str) -> None:
    _require(isinstance(value, bool), f"{label} must be boolean")
    _require(value is expected, f"{label} must be {str(expected).lower()}")


def _status(value: Any, label: str) -> None:
    _require(value == "PASS", f"{label} must be PASS")


def _evidence_ref(value: Any, label: str) -> str:
    ref = _string(value, label)
    _require(len(ref) <= 4096, f"{label} is too long")
    return ref


def _no_pending(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _no_pending(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _no_pending(child, f"{path}[{index}]")
        return
    if value == "PENDING":
        raise ToolGatewayE2EEvidenceError(f"{path} is still PENDING")


def _release_identity(payload: dict[str, Any]) -> dict[str, Any]:
    identity = payload.get("release_identity")
    _require(isinstance(identity, dict), "release_identity is missing")
    assert isinstance(identity, dict)
    git_sha = _string(identity.get("git_sha"), "release_identity.git_sha")
    _require(bool(_SHA40.fullmatch(git_sha)), "release_identity.git_sha must be a full SHA")
    _string(identity.get("version"), "release_identity.version")
    for key in ("tool_gateway_image", "agent_runtime_image", "api_image"):
        image = _string(identity.get(key), f"release_identity.{key}")
        _require(bool(_IMAGE.fullmatch(image)), f"release_identity.{key} must be digest-pinned")
    return identity


def _validate_data_policy(payload: dict[str, Any]) -> None:
    policy = payload.get("data_policy")
    _require(isinstance(policy, dict), "data_policy is missing")
    assert isinstance(policy, dict)
    _bool(policy.get("synthetic_only"), True, "data_policy.synthetic_only")
    _bool(
        policy.get("production_customer_data_used"),
        False,
        "data_policy.production_customer_data_used",
    )
    _bool(
        policy.get("secrets_recorded_in_evidence"),
        False,
        "data_policy.secrets_recorded_in_evidence",
    )


def _validate_readiness(payload: dict[str, Any]) -> None:
    readiness = payload.get("readiness")
    _require(isinstance(readiness, dict), "readiness is missing")
    assert isinstance(readiness, dict)
    _status(readiness.get("status"), "readiness.status")
    _require(readiness.get("adapter_count") == 8, "readiness.adapter_count must be 8")
    _require(
        readiness.get("runtime_binding_count") == 4,
        "readiness.runtime_binding_count must be 4",
    )
    _require(readiness.get("missing_adapters") == [], "readiness.missing_adapters must be empty")
    _require(
        readiness.get("missing_runtime_bindings") == [],
        "readiness.missing_runtime_bindings must be empty",
    )
    _evidence_ref(readiness.get("probe_ref"), "readiness.probe_ref")


def _call_common(tool: str, call: dict[str, Any]) -> None:
    _status(call.get("status"), f"calls.{tool}.status")
    _uuid(call.get("tool_call_id"), f"calls.{tool}.tool_call_id")
    _string(call.get("trace_id"), f"calls.{tool}.trace_id")
    _require(
        call.get("caller_service") == "agent-runtime",
        f"calls.{tool}.caller_service must be agent-runtime",
    )
    _require(
        call.get("resolved_version") == "1.0.0",
        f"calls.{tool}.resolved_version must be 1.0.0",
    )
    _string(call.get("audit_event_id"), f"calls.{tool}.audit_event_id")
    _evidence_ref(call.get("evidence_ref"), f"calls.{tool}.evidence_ref")


def _validate_calls(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    calls = payload.get("calls")
    _require(isinstance(calls, dict), "calls is missing")
    assert isinstance(calls, dict)
    _require(set(calls) == REQUIRED_TOOLS, "calls must contain exactly the 8 P0 tools")
    normalized: dict[str, dict[str, Any]] = {}
    for tool in REQUIRED_TOOLS:
        call = calls.get(tool)
        _require(isinstance(call, dict), f"calls.{tool} must be an object")
        assert isinstance(call, dict)
        _call_common(tool, call)
        normalized[tool] = call

    search = normalized["web.search"]
    _require(search.get("provider") == "brave", "web.search provider must be brave")
    _require(
        search.get("provider_host") == "api.search.brave.com",
        "web.search provider_host must be api.search.brave.com",
    )
    _require(
        isinstance(search.get("result_count"), int) and search["result_count"] > 0,
        "web.search result_count must be positive",
    )

    fetch = normalized["web.fetch"]
    http_status = fetch.get("http_status")
    _require(
        isinstance(http_status, int) and 200 <= http_status < 400,
        "web.fetch http_status must be 2xx/3xx",
    )
    _string(fetch.get("content_type"), "calls.web.fetch.content_type")

    _uuid(normalized["project.query"].get("project_id"), "calls.project.query.project_id")

    for tool in ("asset.read", "media.inspect"):
        ref = _string(normalized[tool].get("asset_ref"), f"calls.{tool}.asset_ref")
        _require(bool(_ASSET_REF.fullmatch(ref)), f"calls.{tool}.asset_ref must be asset://UUID")
        _bool(
            normalized[tool].get("storage_location_exposed"),
            False,
            f"calls.{tool}.storage_location_exposed",
        )

    artifact = normalized["artifact.query"]
    artifact_ref = _string(artifact.get("artifact_ref"), "calls.artifact.query.artifact_ref")
    _require(
        bool(_ARTIFACT_REF.fullmatch(artifact_ref)),
        "calls.artifact.query.artifact_ref must be artifact://UUID",
    )
    _bool(
        artifact.get("storage_location_exposed"),
        False,
        "calls.artifact.query.storage_location_exposed",
    )

    write = normalized["asset.write-derived"]
    _string(write.get("operation_id"), "calls.asset.write-derived.operation_id")
    idempotency_hash = _string(
        write.get("idempotency_key_hash"),
        "calls.asset.write-derived.idempotency_key_hash",
    )
    _require(bool(_SHA256.fullmatch(idempotency_hash)), "write idempotency_key_hash must be sha256")
    write_ref = _string(write.get("asset_ref"), "calls.asset.write-derived.asset_ref")
    _require(bool(_ASSET_REF.fullmatch(write_ref)), "write asset_ref must be asset://UUID")
    _uuid(write.get("source_asset_id"), "calls.asset.write-derived.source_asset_id")
    source_artifact = _string(
        write.get("artifact_ref"),
        "calls.asset.write-derived.artifact_ref",
    )
    _require(
        bool(_ARTIFACT_REF.fullmatch(source_artifact)),
        "write artifact_ref must be artifact://UUID",
    )
    _bool(write.get("rights_inherited"), True, "calls.asset.write-derived.rights_inherited")

    sandbox = normalized["sandbox.execute"]
    _require(sandbox.get("exit_code") == 0, "sandbox.execute exit_code must be 0")
    _require(
        str(sandbox.get("network_policy", "")).lower() == "none",
        "sandbox.execute network_policy must be none",
    )
    return normalized


def _validate_replay(payload: dict[str, Any], calls: dict[str, dict[str, Any]]) -> None:
    replay = payload.get("idempotent_replay")
    _require(isinstance(replay, dict), "idempotent_replay is missing")
    assert isinstance(replay, dict)
    _status(replay.get("status"), "idempotent_replay.status")
    _require(replay.get("tool") == "asset.write-derived", "replay tool must be asset.write-derived")
    first_call = _uuid(replay.get("first_tool_call_id"), "idempotent_replay.first_tool_call_id")
    _uuid(replay.get("replay_tool_call_id"), "idempotent_replay.replay_tool_call_id")
    write = calls["asset.write-derived"]
    _require(first_call == write["tool_call_id"], "replay first_tool_call_id must match write call")
    operation_id = _string(replay.get("operation_id"), "idempotent_replay.operation_id")
    _require(operation_id == write["operation_id"], "replay operation_id must match write call")
    idem_hash = _string(
        replay.get("idempotency_key_hash"),
        "idempotent_replay.idempotency_key_hash",
    )
    _require(idem_hash == write["idempotency_key_hash"], "replay idempotency hash must match write")
    first_ref = _string(replay.get("first_asset_ref"), "idempotent_replay.first_asset_ref")
    replay_ref = _string(replay.get("replay_asset_ref"), "idempotent_replay.replay_asset_ref")
    _require(first_ref == write["asset_ref"], "replay first asset ref must match write")
    _require(replay_ref == first_ref, "replay must return the same derived asset ref")
    _bool(replay.get("replayed"), True, "idempotent_replay.replayed")
    _require(
        replay.get("adapter_invocation_count") == 1,
        "replay adapter_invocation_count must be 1",
    )
    _require(
        replay.get("duplicate_derived_asset_count") == 0,
        "replay duplicate_derived_asset_count must be 0",
    )
    _evidence_ref(replay.get("evidence_ref"), "idempotent_replay.evidence_ref")


def _validate_offload(payload: dict[str, Any], calls: dict[str, dict[str, Any]]) -> None:
    offload = payload.get("result_offload")
    _require(isinstance(offload, dict), "result_offload is missing")
    assert isinstance(offload, dict)
    _status(offload.get("status"), "result_offload.status")
    tool = _string(offload.get("tool"), "result_offload.tool")
    _require(tool in REQUIRED_TOOLS, "result_offload.tool must be a P0 tool")
    tool_call_id = _uuid(offload.get("tool_call_id"), "result_offload.tool_call_id")
    _require(tool_call_id == calls[tool]["tool_call_id"], "offload tool_call_id must match call")
    inline = offload.get("inline_limit_bytes")
    serialized = offload.get("serialized_result_bytes")
    _require(isinstance(inline, int) and inline > 0, "inline_limit_bytes must be positive")
    _require(
        isinstance(serialized, int) and serialized > inline,
        "serialized_result_bytes must exceed inline limit",
    )
    _bool(offload.get("inline_data_present"), False, "result_offload.inline_data_present")
    result_ref = _string(offload.get("result_ref"), "result_offload.result_ref")
    match = _S3_REF.fullmatch(result_ref)
    _require(match is not None, "result_offload.result_ref must be s3ref://...#sha256=...")
    digest = _string(offload.get("sha256"), "result_offload.sha256")
    _require(bool(_SHA256.fullmatch(digest)), "result_offload.sha256 must be sha256")
    assert match is not None
    _require(match.group(1) == digest, "result_offload sha256 must match result_ref")
    _bool(
        offload.get("object_head_verified"),
        True,
        "result_offload.object_head_verified",
    )
    _bool(offload.get("public_url_returned"), False, "result_offload.public_url_returned")
    _evidence_ref(offload.get("evidence_ref"), "result_offload.evidence_ref")


def _validate_audit(payload: dict[str, Any]) -> None:
    audit = payload.get("durable_audit")
    _require(isinstance(audit, dict), "durable_audit is missing")
    assert isinstance(audit, dict)
    _status(audit.get("status"), "durable_audit.status")
    expected = audit.get("expected_call_count")
    persisted = audit.get("persisted_call_count")
    _require(isinstance(expected, int) and expected >= 9, "expected_call_count must be >= 9")
    _require(persisted == expected, "persisted_call_count must equal expected_call_count")
    _require(audit.get("missing_tool_calls") == [], "durable_audit missing_tool_calls must be empty")
    _require(audit.get("cross_tenant_rows") == 0, "durable_audit cross_tenant_rows must be 0")
    _bool(
        audit.get("secret_material_present"),
        False,
        "durable_audit.secret_material_present",
    )
    _evidence_ref(audit.get("evidence_ref"), "durable_audit.evidence_ref")


def _validate_provider(payload: dict[str, Any]) -> None:
    provider = payload.get("provider_search")
    _require(isinstance(provider, dict), "provider_search is missing")
    assert isinstance(provider, dict)
    _status(provider.get("status"), "provider_search.status")
    _require(provider.get("provider") == "brave", "provider_search.provider must be brave")
    _require(
        provider.get("provider_host") == "api.search.brave.com",
        "provider_search.provider_host must be api.search.brave.com",
    )
    _bool(
        provider.get("live_request_observed"),
        True,
        "provider_search.live_request_observed",
    )
    _require(provider.get("provider_http_status") == 200, "provider_search HTTP status must be 200")
    _require(
        isinstance(provider.get("result_count"), int) and provider["result_count"] > 0,
        "provider_search result_count must be positive",
    )
    _bool(provider.get("redirect_followed"), False, "provider_search.redirect_followed")
    _bool(
        provider.get("credential_material_present"),
        False,
        "provider_search.credential_material_present",
    )
    _evidence_ref(provider.get("evidence_ref"), "provider_search.evidence_ref")


def _validate_timestamp(value: Any) -> None:
    captured = _string(value, "captured_at")
    try:
        parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolGatewayE2EEvidenceError("captured_at must be ISO-8601") from exc
    _require(parsed.tzinfo is not None, "captured_at must include timezone")


def validate_contract(payload: dict[str, Any]) -> None:
    _no_pending(payload)
    _require(payload.get("schema_version") == 1, "schema_version must be 1")
    _require(
        payload.get("contract_id") == "lumi-staging-tool-gateway-p0-e2e-v1",
        "contract_id is invalid",
    )
    _require(payload.get("environment") == "staging", "environment must be staging")
    _release_identity(payload)
    _validate_data_policy(payload)
    _validate_readiness(payload)
    calls = _validate_calls(payload)
    _validate_replay(payload, calls)
    _validate_offload(payload, calls)
    _validate_audit(payload)
    _validate_provider(payload)
    _require(payload.get("verdict") == "PASS", "verdict must be PASS")
    _validate_timestamp(payload.get("captured_at"))


def _bind_to_staging_evidence(root: dict[str, Any], contract: dict[str, Any]) -> None:
    release = root.get("release_candidate")
    images = root.get("container_image_set", {}).get("images") if isinstance(root.get("container_image_set"), dict) else None
    _require(isinstance(release, dict), "staging release_candidate is missing")
    _require(isinstance(images, dict), "staging container image set is missing")
    assert isinstance(release, dict)
    assert isinstance(images, dict)
    identity = contract["release_identity"]
    _require(identity["git_sha"] == release.get("git_sha"), "Tool E2E git_sha differs from staging RC")
    _require(identity["version"] == release.get("version"), "Tool E2E version differs from staging RC")
    _require(
        identity["tool_gateway_image"] == images.get("tool-gateway"),
        "Tool E2E Tool Gateway image differs from staging RC",
    )
    _require(
        identity["agent_runtime_image"] == images.get("agent-runtime"),
        "Tool E2E Agent Runtime image differs from staging RC",
    )
    _require(identity["api_image"] == images.get("api"), "Tool E2E API image differs from staging RC")


def validate_evidence(root: dict[str, Any]) -> None:
    if root.get("contract_id") == "lumi-staging-tool-gateway-p0-e2e-v1":
        validate_contract(root)
        return
    contract = root.get("tool_gateway_e2e")
    _require(isinstance(contract, dict), "staging evidence tool_gateway_e2e is missing")
    assert isinstance(contract, dict)
    validate_contract(contract)
    _bind_to_staging_evidence(root, contract)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolGatewayE2EEvidenceError(f"unable to read evidence JSON: {path}") from exc
    _require(isinstance(value, dict), "evidence root must be an object")
    assert isinstance(value, dict)
    return value


def _valid_fixture() -> dict[str, Any]:
    payload = _load(TEMPLATE)
    sha = "a" * 40
    digest = "b" * 64
    asset = "11111111-1111-4111-8111-111111111111"
    artifact = "22222222-2222-4222-8222-222222222222"
    project = "33333333-3333-4333-8333-333333333333"
    payload["release_identity"] = {
        "git_sha": sha,
        "version": "rc-self-test",
        "tool_gateway_image": f"registry/tool-gateway@sha256:{'1' * 64}",
        "agent_runtime_image": f"registry/agent-runtime@sha256:{'2' * 64}",
        "api_image": f"registry/api@sha256:{'3' * 64}",
    }
    payload["readiness"] = {
        "status": "PASS",
        "adapter_count": 8,
        "runtime_binding_count": 4,
        "missing_adapters": [],
        "missing_runtime_bindings": [],
        "probe_ref": "evidence://ready",
    }
    calls = payload["calls"]
    for index, tool in enumerate(sorted(REQUIRED_TOOLS), start=1):
        call = calls[tool]
        call.update(
            {
                "status": "PASS",
                "tool_call_id": f"00000000-0000-4000-8000-{index:012d}",
                "trace_id": f"trace-{index}",
                "caller_service": "agent-runtime",
                "resolved_version": "1.0.0",
                "audit_event_id": f"audit-{index}",
                "evidence_ref": f"evidence://{tool}",
            }
        )
    calls["web.search"].update(
        {"provider": "brave", "provider_host": "api.search.brave.com", "result_count": 2}
    )
    calls["web.fetch"].update({"http_status": 200, "content_type": "text/plain"})
    calls["project.query"]["project_id"] = project
    calls["asset.read"].update(
        {"asset_ref": f"asset://{asset}", "storage_location_exposed": False}
    )
    calls["artifact.query"].update(
        {"artifact_ref": f"artifact://{artifact}", "storage_location_exposed": False}
    )
    calls["media.inspect"].update(
        {"asset_ref": f"asset://{asset}", "storage_location_exposed": False}
    )
    write = calls["asset.write-derived"]
    write.update(
        {
            "operation_id": "operation-self-test",
            "idempotency_key_hash": digest,
            "asset_ref": f"asset://{asset}",
            "source_asset_id": asset,
            "artifact_ref": f"artifact://{artifact}",
            "rights_inherited": True,
        }
    )
    calls["sandbox.execute"].update({"exit_code": 0, "network_policy": "none"})
    payload["idempotent_replay"] = {
        "status": "PASS",
        "tool": "asset.write-derived",
        "first_tool_call_id": write["tool_call_id"],
        "replay_tool_call_id": "99999999-9999-4999-8999-999999999999",
        "operation_id": write["operation_id"],
        "idempotency_key_hash": digest,
        "first_asset_ref": write["asset_ref"],
        "replay_asset_ref": write["asset_ref"],
        "replayed": True,
        "adapter_invocation_count": 1,
        "duplicate_derived_asset_count": 0,
        "evidence_ref": "evidence://replay",
    }
    payload["result_offload"] = {
        "status": "PASS",
        "tool": "sandbox.execute",
        "tool_call_id": calls["sandbox.execute"]["tool_call_id"],
        "inline_limit_bytes": 65536,
        "serialized_result_bytes": 70000,
        "inline_data_present": False,
        "result_ref": f"s3ref://bucket/tool-results/test#sha256={digest}",
        "sha256": digest,
        "object_head_verified": True,
        "public_url_returned": False,
        "evidence_ref": "evidence://offload",
    }
    payload["durable_audit"] = {
        "status": "PASS",
        "expected_call_count": 9,
        "persisted_call_count": 9,
        "missing_tool_calls": [],
        "cross_tenant_rows": 0,
        "secret_material_present": False,
        "evidence_ref": "evidence://audit",
    }
    payload["provider_search"] = {
        "status": "PASS",
        "provider": "brave",
        "provider_host": "api.search.brave.com",
        "live_request_observed": True,
        "provider_http_status": 200,
        "result_count": 2,
        "redirect_followed": False,
        "credential_material_present": False,
        "evidence_ref": "evidence://provider",
    }
    payload["verdict"] = "PASS"
    payload["captured_at"] = datetime.now(UTC).isoformat()
    return payload


def self_test() -> None:
    valid = _valid_fixture()
    validate_contract(valid)
    broken = copy.deepcopy(valid)
    broken["idempotent_replay"]["duplicate_derived_asset_count"] = 1
    try:
        validate_contract(broken)
    except ToolGatewayE2EEvidenceError:
        pass
    else:
        raise ToolGatewayE2EEvidenceError("self-test accepted duplicate derived asset")
    broken = copy.deepcopy(valid)
    broken["provider_search"]["live_request_observed"] = False
    try:
        validate_contract(broken)
    except ToolGatewayE2EEvidenceError:
        pass
    else:
        raise ToolGatewayE2EEvidenceError("self-test accepted non-live web search evidence")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.evidence is not None:
        validate_evidence(_load(args.evidence))
    if not args.self_test and args.evidence is None:
        parser.error("one of --self-test or --evidence is required")
    print("Tool Gateway P0 staging E2E evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
