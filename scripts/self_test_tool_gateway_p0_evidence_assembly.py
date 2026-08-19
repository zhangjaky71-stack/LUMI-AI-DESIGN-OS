#!/usr/bin/env python3
from __future__ import annotations

import copy

from assemble_tool_gateway_p0_e2e_evidence import AssembleError, assemble
from validate_tool_gateway_e2e_evidence import validate_contract

_SHA = "a" * 40
_DIGEST = "b" * 64
_ASSET_ID = "11111111-1111-4111-8111-111111111111"
_ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
_PROJECT_ID = "33333333-3333-4333-8333-333333333333"
_SOURCE_ASSET_ID = "44444444-4444-4444-8444-444444444444"
_REPLAY_ID = "99999999-9999-4999-8999-999999999999"
_OFFLOAD_ID = "88888888-8888-4888-8888-888888888888"


def _call_id(index: int) -> str:
    return f"00000000-0000-4000-8000-{index:012d}"


def _result(
    tool: str,
    call_id: str,
    *,
    data: dict[str, object],
    refs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tool_call_id": call_id,
        "status": "succeeded",
        "resolved_name": tool,
        "resolved_version": "1.0.0",
        "summary": f"{tool} synthetic success",
        "resource_refs": refs or [],
        "replayed": False,
        "approval_id": None,
        "data": data,
    }


def _fixtures() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, str],
]:
    staging: dict[str, object] = {
        "release_candidate": {"git_sha": _SHA, "version": "rc-self-test"},
        "container_image_set": {
            "images": {
                "api": f"registry/api@sha256:{'1' * 64}",
                "agent-runtime": f"registry/agent-runtime@sha256:{'2' * 64}",
                "tool-gateway": f"registry/tool-gateway@sha256:{'3' * 64}",
            }
        },
        "data_policy": {
            "production_customer_data_used": False,
            "test_data_only": True,
        },
    }

    tools = [
        "web.search",
        "web.fetch",
        "project.query",
        "asset.read",
        "artifact.query",
        "media.inspect",
        "asset.write-derived",
        "sandbox.execute",
    ]
    calls: dict[str, object] = {}
    call_ids: dict[str, str] = {}
    for index, tool in enumerate(tools, start=1):
        call_id = _call_id(index)
        call_ids[tool] = call_id
        arguments: dict[str, object] = {}
        data: dict[str, object] = {}
        refs: list[str] = []
        if tool == "web.search":
            arguments = {"query": "lumi design", "limit": 5}
            data = {
                "results": [
                    {
                        "title": "LUMI",
                        "url": "https://example.com/lumi",
                        "snippet": "Synthetic search result",
                    }
                ]
            }
        elif tool == "web.fetch":
            arguments = {"url": "https://example.com/"}
            data = {
                "url": "https://example.com/",
                "status": 200,
                "content_type": "text/html",
                "text": "ok",
            }
        elif tool == "project.query":
            arguments = {"query": "project.summary"}
            data = {
                "project_id": _PROJECT_ID,
                "name": "Synthetic Project",
                "status": "active",
                "summary": {},
            }
        elif tool == "asset.read":
            arguments = {"asset_id": _SOURCE_ASSET_ID}
            data = {"asset_id": _SOURCE_ASSET_ID, "status": "ready", "files": []}
            refs = [f"asset://{_SOURCE_ASSET_ID}"]
        elif tool == "artifact.query":
            arguments = {"artifact_id": _ARTIFACT_ID}
            data = {"artifact_id": _ARTIFACT_ID, "title": "Poster"}
            refs = [f"artifact://{_ARTIFACT_ID}"]
        elif tool == "media.inspect":
            arguments = {"asset_id": _SOURCE_ASSET_ID}
            data = {"asset_id": _SOURCE_ASSET_ID, "kind": "image", "files": []}
            refs = [f"asset://{_SOURCE_ASSET_ID}"]
        elif tool == "asset.write-derived":
            arguments = {
                "source_asset_id": _SOURCE_ASSET_ID,
                "artifact_ref": f"artifact://{_ARTIFACT_ID}",
                "metadata": {"variant": "self-test"},
            }
            data = {"asset_id": _ASSET_ID, "status": "ready"}
            refs = [f"asset://{_ASSET_ID}"]
        elif tool == "sandbox.execute":
            arguments = {"command": ["python", "-c", "print('ok')"]}
            data = {"exit_code": 0, "network_policy": "none", "stdout": "ok\n"}
        calls[tool] = {
            "request": {
                "tool_call_id": call_id,
                "trace_id": f"trace-{index}",
                "idempotency_key_present": tool
                in {"asset.write-derived", "sandbox.execute"},
                "arguments": arguments,
            },
            "result": _result(tool, call_id, data=data, refs=refs),
        }

    probe: dict[str, object] = {
        "schema_version": 1,
        "caller_service": "agent-runtime",
        "scope": {
            "organization_id": "55555555-5555-4555-8555-555555555555",
            "agent_run_id": "66666666-6666-4666-8666-666666666666",
            "task_id": "77777777-7777-4777-8777-777777777777",
            "source_asset_id": _SOURCE_ASSET_ID,
            "artifact_id": _ARTIFACT_ID,
        },
        "calls": calls,
        "idempotent_replay": {
            "first_tool_call_id": call_ids["asset.write-derived"],
            "replay_tool_call_id": _REPLAY_ID,
            "first_asset_ref": f"asset://{_ASSET_ID}",
            "replay_asset_ref": f"asset://{_ASSET_ID}",
            "replayed": True,
            "same_asset_ref": True,
        },
        "result_offload": {
            "tool": "sandbox.execute",
            "tool_call_id": _OFFLOAD_ID,
            "trace_id": "trace-offload",
            "result_ref": f"s3ref://lumi-staging-123456789012-us-east-1-exports/"
            f"tool-results/v1/test#sha256={_DIGEST}",
            "inline_data_present": False,
        },
    }

    event_ids = {
        **{call_id: f"audit-{tool}" for tool, call_id in call_ids.items()},
        _REPLAY_ID: "audit-replay",
        _OFFLOAD_ID: "audit-offload",
    }
    db: dict[str, object] = {
        "schema_version": 1,
        "scope": {"project_id": _PROJECT_ID},
        "tool_call_ids": call_ids,
        "replay_tool_call_id": _REPLAY_ID,
        "offload_tool_call_id": _OFFLOAD_ID,
        "audit": {
            "expected_call_count": 10,
            "persisted_call_count": 10,
            "missing_tool_calls": [],
            "cross_tenant_rows": 0,
            "secret_material_present": False,
            "event_ids_by_tool_call_id": event_ids,
        },
        "idempotency": {
            "operation_id": "operation-self-test",
            "operation_type": "tool:asset.write-derived:1.0.0",
            "status": "succeeded",
            "idempotency_key_hash": _DIGEST,
        },
        "derived_asset": {
            "derived_asset_id": _ASSET_ID,
            "derived_asset_ref": f"asset://{_ASSET_ID}",
            "matching_asset_ids": [_ASSET_ID],
            "adapter_invocation_count": 1,
            "duplicate_derived_asset_count": 0,
        },
        "rights": {
            "rights_inherited": True,
            "mismatched_fields": [],
        },
    }

    result_ref = probe["result_offload"]["result_ref"]  # type: ignore[index]
    s3: dict[str, object] = {
        "schema_version": 1,
        "result_ref": result_ref,
        "sha256": _DIGEST,
        "content_length": 70000,
        "inline_limit_bytes": 65536,
        "content_type": "application/json",
        "metadata_sha256_verified": True,
        "object_head_verified": True,
        "public_url_returned": False,
    }
    readiness: dict[str, object] = {
        "schema_version": 1,
        "http_status": 200,
        "response": {
            "service": "tool-gateway",
            "status": "ok",
            "adapter_count": 8,
            "runtime_binding_count": 4,
            "missing_adapters": [],
            "missing_runtime_bindings": [],
        },
    }
    search: dict[str, object] = {
        "schema_version": 1,
        "provider": "brave",
        "provider_host": "api.search.brave.com",
        "live_request_observed": True,
        "provider_http_status": 200,
        "result_count": 1,
        "redirect_followed": False,
        "credential_material_present": False,
        "tool_call_id": call_ids["web.search"],
        "trace_id": "trace-1",
        "observation_basis": "synthetic assembler self-test",
        "direct_packet_capture": False,
    }
    refs = {
        "probe": "evidence://probe",
        "db": "evidence://db",
        "s3": "evidence://s3",
        "readiness": "evidence://readiness",
        "search": "evidence://search",
    }
    return staging, probe, db, s3, readiness, search, refs


def _must_fail(label: str, fn: object) -> None:
    try:
        assert callable(fn)
        fn()
    except AssembleError:
        return
    raise RuntimeError(f"assembler self-test accepted invalid evidence: {label}")


def main() -> int:
    staging, probe, db, s3, readiness, search, refs = _fixtures()
    payload = assemble(
        staging=staging,
        probe=probe,
        db=db,
        s3=s3,
        readiness=readiness,
        search=search,
        refs=refs,
    )
    validate_contract(payload)

    broken_db = copy.deepcopy(db)
    broken_db["derived_asset"]["duplicate_derived_asset_count"] = 1  # type: ignore[index]
    _must_fail(
        "duplicate derived Asset",
        lambda: assemble(
            staging=staging,
            probe=probe,
            db=broken_db,
            s3=s3,
            readiness=readiness,
            search=search,
            refs=refs,
        ),
    )

    broken_s3 = copy.deepcopy(s3)
    broken_s3["result_ref"] = f"s3ref://other/tool-results/v1/x#sha256={_DIGEST}"
    _must_fail(
        "S3 ref mismatch",
        lambda: assemble(
            staging=staging,
            probe=probe,
            db=db,
            s3=broken_s3,
            readiness=readiness,
            search=search,
            refs=refs,
        ),
    )

    broken_readiness = copy.deepcopy(readiness)
    broken_readiness["response"]["adapter_count"] = 7  # type: ignore[index]
    _must_fail(
        "readiness adapter deficit",
        lambda: assemble(
            staging=staging,
            probe=probe,
            db=db,
            s3=s3,
            readiness=broken_readiness,
            search=search,
            refs=refs,
        ),
    )

    print("Tool Gateway P0 evidence assembler self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
