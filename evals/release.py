from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .gate import compare_runs
from .models import SuiteDefinition

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_FLOATING = {"", "latest", "main", "master", "dev", "unknown", "*", "unversioned"}


class ReleaseGateError(RuntimeError):
    """Raised when an AI release cannot be evaluated safely."""


def _string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReleaseGateError(f"{key} must be a non-empty string")
    value = value.strip()
    if value.lower() in _FLOATING:
        raise ReleaseGateError(f"{key} must be an exact immutable identity, not {value!r}")
    return value


def _versions(raw: dict[str, Any], key: str) -> dict[str, str]:
    value = raw.get(key)
    if not isinstance(value, dict) or not value:
        raise ReleaseGateError(f"{key} must be a non-empty object")
    result: dict[str, str] = {}
    for name, version in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ReleaseGateError(f"{key} contains an invalid name")
        if not isinstance(version, str) or version.strip().lower() in _FLOATING:
            raise ReleaseGateError(f"{key}.{name} must be an exact version")
        result[name] = version.strip()
    return result


@dataclass(frozen=True)
class BenchmarkProfileIdentity:
    name: str
    version: str

    @classmethod
    def from_dict(cls, suite: str, raw: Any) -> "BenchmarkProfileIdentity":
        if not isinstance(raw, dict):
            raise ReleaseGateError(f"benchmark_profiles.{suite} must be an object")
        return cls(
            name=_string(raw, "name"),
            version=_string(raw, "version"),
        )


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    role: str
    git_sha: str
    agent_version: str
    system_prompt_hash: str
    skill_versions: dict[str, str]
    recipe_version: str
    model_routing_policy_version: str
    critic_version: str
    constraint_policy_version: str
    context_policy_version: str
    suite_versions: dict[str, str]
    benchmark_profiles: dict[str, BenchmarkProfileIdentity]
    evidence_mode: str
    source: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, expected_role: str | None = None) -> "ReleaseManifest":
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ReleaseGateError("release manifest schema_version must be 1")
        role = _string(raw, "role")
        if role not in {"baseline", "candidate"}:
            raise ReleaseGateError("role must be baseline or candidate")
        if expected_role and role != expected_role:
            raise ReleaseGateError(f"expected {expected_role} manifest, got {role}")
        git_sha = _string(raw, "git_sha").lower()
        if not _SHA40.fullmatch(git_sha):
            raise ReleaseGateError("git_sha must be an exact 40-character hexadecimal SHA")
        evidence_mode = _string(raw, "evidence_mode")
        if evidence_mode not in {"fixture", "recorded", "live"}:
            raise ReleaseGateError("evidence_mode must be fixture, recorded, or live")
        source = _string(raw, "source")
        if source not in {"production", "candidate", "fixture"}:
            raise ReleaseGateError("source must be production, candidate, or fixture")
        suite_versions = _versions(raw, "suite_versions")
        profiles_raw = raw.get("benchmark_profiles")
        if not isinstance(profiles_raw, dict) or not profiles_raw:
            raise ReleaseGateError("benchmark_profiles must be a non-empty object")
        benchmark_profiles = {
            suite: BenchmarkProfileIdentity.from_dict(suite, profile)
            for suite, profile in profiles_raw.items()
            if isinstance(suite, str) and suite.strip()
        }
        if set(benchmark_profiles) != set(suite_versions):
            raise ReleaseGateError("benchmark_profiles must pin exactly the same suites as suite_versions")
        return cls(
            release_id=_string(raw, "release_id"),
            role=role,
            git_sha=git_sha,
            agent_version=_string(raw, "agent_version"),
            system_prompt_hash=_string(raw, "system_prompt_hash"),
            skill_versions=_versions(raw, "skill_versions"),
            recipe_version=_string(raw, "recipe_version"),
            model_routing_policy_version=_string(raw, "model_routing_policy_version"),
            critic_version=_string(raw, "critic_version"),
            constraint_policy_version=_string(raw, "constraint_policy_version"),
            context_policy_version=_string(raw, "context_policy_version"),
            suite_versions=suite_versions,
            benchmark_profiles=benchmark_profiles,
            evidence_mode=evidence_mode,
            source=source,
        )

    def fingerprint(self) -> str:
        payload = {
            "release_id": self.release_id,
            "git_sha": self.git_sha,
            "agent_version": self.agent_version,
            "system_prompt_hash": self.system_prompt_hash,
            "skill_versions": self.skill_versions,
            "recipe_version": self.recipe_version,
            "model_routing_policy_version": self.model_routing_policy_version,
            "critic_version": self.critic_version,
            "constraint_policy_version": self.constraint_policy_version,
            "context_policy_version": self.context_policy_version,
            "suite_versions": self.suite_versions,
            "benchmark_profiles": {
                suite: {"name": profile.name, "version": profile.version}
                for suite, profile in sorted(self.benchmark_profiles.items())
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_run_identity(manifest: ReleaseManifest, run: dict[str, Any], suite: str) -> None:
    expected_suite_version = manifest.suite_versions.get(suite)
    if expected_suite_version is None:
        raise ReleaseGateError(f"manifest does not pin suite {suite}")
    if run.get("suite") != suite or run.get("suite_version") != expected_suite_version:
        raise ReleaseGateError(f"run identity mismatch for suite {suite}")
    if run.get("git_sha") != manifest.git_sha:
        raise ReleaseGateError(f"run git_sha does not match manifest for suite {suite}")
    candidate = run.get("candidate")
    if not isinstance(candidate, dict):
        raise ReleaseGateError(f"run candidate identity missing for suite {suite}")
    expected_profile = manifest.benchmark_profiles.get(suite)
    if expected_profile is None:
        raise ReleaseGateError(f"manifest does not pin benchmark profile for suite {suite}")
    if candidate.get("name") != expected_profile.name or candidate.get("version") != expected_profile.version:
        raise ReleaseGateError(f"benchmark profile mismatch for suite {suite}")


def _critical_case_checks(run: dict[str, Any], metrics: dict[str, float]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    cases = run.get("cases")
    if not isinstance(cases, list):
        raise ReleaseGateError("run.cases must be an array")
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("scores"), dict):
            raise ReleaseGateError("every run case must contain scores")
        scores = case["scores"]
        for metric, maximum in metrics.items():
            if metric not in scores:
                continue
            value = scores[metric]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ReleaseGateError(f"critical metric {metric} must be numeric")
            checks.append(
                {
                    "suite": run.get("suite"),
                    "case_id": case.get("case_id"),
                    "metric": metric,
                    "value": float(value),
                    "maximum": float(maximum),
                    "passed": float(value) <= float(maximum),
                }
            )
    return checks


def _supplemental_checks(policy: dict[str, Any], evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    required = policy.get("required_supplemental_evidence", [])
    if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
        raise ReleaseGateError("policy.required_supplemental_evidence must be a string array")
    statistical = policy.get("statistical_evidence", [])
    if not isinstance(statistical, list) or not all(isinstance(item, str) and item for item in statistical):
        raise ReleaseGateError("policy.statistical_evidence must be a string array")
    minimum_sample = policy.get("minimum_statistical_sample_size", 1)
    if not isinstance(minimum_sample, int) or isinstance(minimum_sample, bool) or minimum_sample < 1:
        raise ReleaseGateError("minimum_statistical_sample_size must be an integer >= 1")

    supplied = evidence or {}
    checks: list[dict[str, Any]] = []
    for name in required:
        item = supplied.get(name)
        has_ref = isinstance(item, dict) and isinstance(item.get("evidence_ref"), str) and bool(item["evidence_ref"].strip())
        passed = isinstance(item, dict) and item.get("status") == "PASS" and has_ref
        statistical_ok = True
        sample_size = None
        confidence_method = None
        if name in statistical:
            if isinstance(item, dict):
                sample_size = item.get("sample_size")
                confidence_method = item.get("confidence_method")
            statistical_ok = (
                isinstance(sample_size, int)
                and not isinstance(sample_size, bool)
                and sample_size >= minimum_sample
                and isinstance(confidence_method, str)
                and bool(confidence_method.strip())
            )
            passed = passed and statistical_ok
        checks.append(
            {
                "name": name,
                "passed": passed,
                "evidence_ref": item.get("evidence_ref") if isinstance(item, dict) else None,
                "statistical_required": name in statistical,
                "sample_size": sample_size,
                "confidence_method": confidence_method,
                "statistical_passed": statistical_ok,
            }
        )
    return checks


def evaluate_release(
    policy: dict[str, Any],
    baseline_manifest: ReleaseManifest,
    candidate_manifest: ReleaseManifest,
    suite_pairs: dict[str, tuple[SuiteDefinition, dict[str, Any], dict[str, Any]]],
    *,
    mode: str = "contract",
    supplemental_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"contract", "release"}:
        raise ReleaseGateError("mode must be contract or release")
    required = policy.get("required_suites")
    if not isinstance(required, list) or not required or not all(isinstance(item, str) for item in required):
        raise ReleaseGateError("policy.required_suites must be a non-empty string array")
    missing = sorted(set(required) - set(suite_pairs))
    if missing:
        raise ReleaseGateError(f"required suites missing: {missing}")
    if mode == "release":
        if baseline_manifest.source != "production" or baseline_manifest.evidence_mode == "fixture":
            raise ReleaseGateError("release mode requires a real production baseline, not fixture evidence")
        if candidate_manifest.source != "candidate" or candidate_manifest.evidence_mode == "fixture":
            raise ReleaseGateError("release mode requires recorded/live candidate evidence")

    critical_raw = policy.get("critical_case_metrics", {})
    if not isinstance(critical_raw, dict):
        raise ReleaseGateError("policy.critical_case_metrics must be an object")
    critical_metrics: dict[str, float] = {}
    for metric, maximum in critical_raw.items():
        if not isinstance(metric, str) or not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            raise ReleaseGateError("critical_case_metrics must map metric names to numeric maxima")
        critical_metrics[metric] = float(maximum)

    suite_results: list[dict[str, Any]] = []
    critical_checks: list[dict[str, Any]] = []
    for suite_name in required:
        suite, baseline_run, candidate_run = suite_pairs[suite_name]
        _validate_run_identity(baseline_manifest, baseline_run, suite_name)
        _validate_run_identity(candidate_manifest, candidate_run, suite_name)
        gate = compare_runs(suite, baseline_run, candidate_run)
        suite_results.append(gate)
        critical_checks.extend(_critical_case_checks(candidate_run, critical_metrics))

    supplemental_checks = _supplemental_checks(policy, supplemental_evidence) if mode == "release" else []
    critical_passed = all(check["passed"] for check in critical_checks)
    suites_passed = all(item["passed"] for item in suite_results)
    supplemental_passed = all(check["passed"] for check in supplemental_checks)
    passed = critical_passed and suites_passed and supplemental_passed
    decision_payload = {
        "baseline_fingerprint": baseline_manifest.fingerprint(),
        "candidate_fingerprint": candidate_manifest.fingerprint(),
        "mode": mode,
        "suite_results": suite_results,
        "critical_case_checks": critical_checks,
        "supplemental_checks": supplemental_checks,
        "passed": passed,
    }
    decision_id = hashlib.sha256(json.dumps(decision_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    return {"schema_version": 1, "decision_id": decision_id, **decision_payload}
