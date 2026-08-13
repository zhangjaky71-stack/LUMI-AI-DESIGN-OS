from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/models/provider-matrix-manifest.json"

ALLOWED_LIFECYCLE = {"stable", "preview", "deprecated", "legacy", "shutdown"}
ALLOWED_BENCHMARK = {"NOT_MEASURED", "OFFLINE_SPECIFIED", "MEASURED_LIVE"}
OFFICIAL_HOSTS = {
    "openai": {"developers.openai.com", "platform.openai.com", "openai.com"},
    "google": {"ai.google.dev"},
    "anthropic": {"platform.claude.com", "docs.anthropic.com", "anthropic.com"},
    "black-forest-labs": {"docs.bfl.ai", "docs.bfl.ml", "bfl.ai"},
    "runway": {"docs.dev.runwayml.com", "runwayml.com"},
}


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load {path.relative_to(ROOT)}: {exc}") from exc


def require_text(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must be non-empty string")
    return value


def parse_date(value: Any, field: str) -> date:
    text = require_text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO date") from exc


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    version = require_text(manifest.get("registry_version"), "manifest.registry_version")
    observed_at = parse_date(manifest.get("observed_at"), "manifest.observed_at")
    expires_at = parse_date(manifest.get("pricing_expires_at"), "manifest.pricing_expires_at")
    require(0 < (expires_at - observed_at).days <= 30, "pricing expiry must be within 30 days of observation")

    required_providers = manifest.get("required_providers")
    required_modalities = manifest.get("required_modalities")
    expected_counts = manifest.get("expected_counts")
    require(isinstance(required_providers, list) and len(required_providers) >= 5, "at least 5 providers required")
    require(isinstance(required_modalities, list) and required_modalities, "required modalities missing")
    require(isinstance(expected_counts, dict), "expected counts missing")

    source_doc = load_json(ROOT / require_text(manifest.get("source_catalog"), "manifest.source_catalog"))
    require(source_doc.get("registry_version") == version, "source registry version mismatch")
    sources_raw = source_doc.get("sources")
    require(isinstance(sources_raw, list) and sources_raw, "provider source catalog empty")
    sources: dict[str, dict[str, Any]] = {}
    for item in sources_raw:
        require(isinstance(item, dict), "source row must be object")
        source_id = require_text(item.get("source_id"), "source.source_id")
        provider = require_text(item.get("provider"), f"{source_id}.provider")
        require(provider in required_providers, f"{source_id}: provider not declared")
        require(source_id not in sources, f"duplicate source id: {source_id}")
        require(parse_date(item.get("observed_at"), f"{source_id}.observed_at") <= observed_at, f"{source_id}: source date after registry observation")
        url = require_text(item.get("url"), f"{source_id}.url")
        host = urlparse(url).hostname
        require(host in OFFICIAL_HOSTS[provider], f"{source_id}: non-first-party host {host}")
        sources[source_id] = item

    provider_files = sorted(ROOT.glob(require_text(manifest.get("provider_glob"), "manifest.provider_glob")))
    require(len(provider_files) == len(required_providers), "provider file count mismatch")

    provider_names: set[str] = set()
    models: dict[str, dict[str, Any]] = {}
    lifecycle_counts: Counter[str] = Counter()
    benchmark_counts: Counter[str] = Counter()
    route_eligible_count = 0
    modality_coverage: set[str] = set()

    for path in provider_files:
        doc = load_json(path)
        provider = require_text(doc.get("provider"), f"{path.name}.provider")
        require(provider in required_providers, f"{path.name}: unexpected provider {provider}")
        require(provider not in provider_names, f"duplicate provider file: {provider}")
        provider_names.add(provider)
        require(parse_date(doc.get("observed_at"), f"{provider}.observed_at") == observed_at, f"{provider}: observed_at mismatch")
        provider_expiry = parse_date(doc.get("pricing_expires_at"), f"{provider}.pricing_expires_at")
        require(provider_expiry == expires_at, f"{provider}: pricing expiry mismatch")
        rows = doc.get("models")
        require(isinstance(rows, list) and rows, f"{provider}: model list empty")

        for row in rows:
            require(isinstance(row, dict), f"{provider}: model row must be object")
            registry_id = require_text(row.get("registry_id"), f"{provider}.registry_id")
            require(registry_id.startswith(f"{provider}:"), f"{registry_id}: wrong provider prefix")
            require(registry_id not in models, f"duplicate registry_id: {registry_id}")
            require_text(row.get("model_id"), f"{registry_id}.model_id")
            modalities = row.get("modalities")
            require(isinstance(modalities, list) and modalities and all(isinstance(x, str) and x for x in modalities), f"{registry_id}: modalities required")
            modality_coverage.update(modalities)
            lifecycle = require_text(row.get("lifecycle"), f"{registry_id}.lifecycle")
            require(lifecycle in ALLOWED_LIFECYCLE, f"{registry_id}: invalid lifecycle")
            lifecycle_counts[lifecycle] += 1
            route_eligible = row.get("route_eligible")
            require(isinstance(route_eligible, bool), f"{registry_id}: route_eligible must be bool")
            if route_eligible:
                route_eligible_count += 1
                require(lifecycle not in {"deprecated", "legacy", "shutdown"}, f"{registry_id}: inactive lifecycle cannot be route eligible")
            else:
                if lifecycle in {"stable", "preview"}:
                    require(bool(row.get("notes")), f"{registry_id}: active but excluded model needs notes")

            capabilities = row.get("documented_capabilities")
            require(isinstance(capabilities, dict) and capabilities, f"{registry_id}: documented capabilities missing")
            roles = row.get("documented_roles")
            require(isinstance(roles, list), f"{registry_id}: roles must be a list")
            if route_eligible:
                require(roles, f"{registry_id}: route-eligible model needs documented role")

            pricing = row.get("pricing")
            require(isinstance(pricing, list), f"{registry_id}: pricing must be list")
            if lifecycle not in {"deprecated", "legacy", "shutdown"}:
                require(pricing, f"{registry_id}: active candidate needs documented pricing")
            for price in pricing:
                require(isinstance(price, dict), f"{registry_id}: price row must be object")
                require_text(price.get("metric"), f"{registry_id}.price.metric")
                numeric_fields = [key for key in ("usd", "usd_per_million", "credits") if key in price]
                require(numeric_fields, f"{registry_id}: price row needs numeric value")
                for key in numeric_fields:
                    value = price[key]
                    require(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0, f"{registry_id}: invalid {key}")

            benchmark_status = require_text(row.get("benchmark_status"), f"{registry_id}.benchmark_status")
            require(benchmark_status in ALLOWED_BENCHMARK, f"{registry_id}: invalid benchmark status")
            benchmark_counts[benchmark_status] += 1
            quality = row.get("quality")
            latency = row.get("latency_ms")
            if benchmark_status != "MEASURED_LIVE":
                require(quality == "NOT_MEASURED", f"{registry_id}: unmeasured quality must be NOT_MEASURED")
                require(latency == "NOT_MEASURED", f"{registry_id}: unmeasured latency must be NOT_MEASURED")
            else:
                require(isinstance(quality, dict), f"{registry_id}: measured quality needs evidence object")
                require(isinstance(latency, dict), f"{registry_id}: measured latency needs evidence object")

            source_ids = row.get("sources")
            require(isinstance(source_ids, list) and source_ids, f"{registry_id}: official sources required")
            for source_id in source_ids:
                require(source_id in sources, f"{registry_id}: unknown source {source_id}")
                require(sources[source_id]["provider"] == provider, f"{registry_id}: cross-provider factual source {source_id}")
            models[registry_id] = row

    require(provider_names == set(required_providers), "required provider coverage mismatch")
    for modality in required_modalities:
        require(modality in modality_coverage, f"required modality not covered: {modality}")

    counts = expected_counts
    require(len(provider_names) == counts.get("providers"), "provider count mismatch")
    require(len(models) == counts.get("models"), f"model count mismatch: {len(models)}")
    require(route_eligible_count == counts.get("route_eligible_models"), "route eligible count mismatch")
    for status, expected in counts.get("benchmark_status", {}).items():
        require(benchmark_counts[status] == expected, f"benchmark status count mismatch for {status}")
    for lifecycle, expected in counts.get("lifecycle", {}).items():
        require(lifecycle_counts[lifecycle] == expected, f"lifecycle count mismatch for {lifecycle}: {lifecycle_counts[lifecycle]}")

    route_doc = load_json(ROOT / require_text(manifest.get("route_policy"), "manifest.route_policy"))
    require(route_doc.get("registry_version") == version, "route policy version mismatch")
    require(route_doc.get("selection_policy") == "CANDIDATE_SET_ONLY_UNTIL_LIVE_BENCHMARK", "routes must not preselect winners")
    routes = route_doc.get("routes")
    require(isinstance(routes, list) and routes, "route policy empty")
    route_names: set[str] = set()
    for route in routes:
        require(isinstance(route, dict), "route must be object")
        route_name = require_text(route.get("route"), "route.route")
        require(route_name not in route_names, f"duplicate route: {route_name}")
        route_names.add(route_name)
        require(route.get("selected_primary") is None, f"{route_name}: NODE-07 must not select primary before benchmark")
        candidates = route.get("candidates")
        require(isinstance(candidates, list) and candidates, f"{route_name}: candidates missing")
        has_preview = False
        has_stable = False
        for candidate in candidates:
            require(candidate in models, f"{route_name}: unknown candidate {candidate}")
            model = models[candidate]
            require(model["route_eligible"] is True, f"{route_name}: excluded candidate {candidate}")
            has_preview = has_preview or model["lifecycle"] == "preview"
            has_stable = has_stable or model["lifecycle"] == "stable"
        if has_preview and not has_stable:
            fallbacks = route.get("stable_fallback_candidates")
            require(isinstance(fallbacks, list) and fallbacks, f"{route_name}: preview-only route needs stable fallback")
            for fallback in fallbacks:
                require(fallback in models and models[fallback]["lifecycle"] == "stable" and models[fallback]["route_eligible"], f"{route_name}: invalid stable fallback {fallback}")

    suite = load_json(ROOT / require_text(manifest.get("benchmark_suite"), "manifest.benchmark_suite"))
    require(suite.get("version") == version, "benchmark suite version mismatch")
    require(suite.get("observed_at") == observed_at.isoformat(), "benchmark suite observed_at mismatch")
    require(suite.get("execution_status") == "SPECIFIED_NOT_RUN", "NODE-07 live benchmark must remain SPECIFIED_NOT_RUN")
    require(suite.get("live_policy") == "SKIPPED_WITHOUT_PROVIDER_KEY_AND_POSITIVE_BUDGET", "live skip policy missing")
    groups = suite.get("benchmark_groups")
    require(isinstance(groups, list) and groups, "benchmark groups missing")
    suite_routes = {r for group in groups for r in group.get("routes", [])}
    require(suite_routes == route_names, "every route must map to a benchmark group")

    print(f"PASS model provider registry v{version}")
    print(f"PASS providers={len(provider_names)} models={len(models)} route_eligible={route_eligible_count}")
    print("PASS lifecycle=" + ", ".join(f"{k}:{lifecycle_counts[k]}" for k in ["stable", "preview", "deprecated"]))
    print(f"PASS official_sources={len(sources)} routes={len(route_names)}")
    print("PASS benchmark_status=NOT_MEASURED:" + str(benchmark_counts["NOT_MEASURED"]))
    print("PASS no provider winner selected before LUMI live benchmark")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"FAIL model provider contract: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
