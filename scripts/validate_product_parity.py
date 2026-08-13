from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/product/capability-matrix-manifest.json"

ALLOWED_TARGETS = {"PARITY", "SUPERSET", "DEFER", "OUT-OF-SCOPE"}
ALLOWED_COMPETITOR_STATUS = {"confirmed", "confirmed_marketing", "not_confirmed"}
ALLOWED_LUMI_STATUS = {"PLANNED", "IN_PROGRESS", "IMPLEMENTED", "COMPLETE", "DEFERRED"}
NODE_RE = re.compile(r"^NODE-\d{2}$")
CAPABILITY_RE = re.compile(r"^[A-G]\d{2}$")
CASE_RE = re.compile(r"^PARITY-[A-G]\d{2}$")


class ContractError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path.relative_to(ROOT)}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate_string(value: Any, field: str, *, nonempty: bool = True) -> str:
    require(isinstance(value, str), f"{field} must be a string")
    if nonempty:
        require(bool(value.strip()), f"{field} must not be empty")
    return value


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    matrix_version = validate_string(manifest.get("matrix_version"), "manifest.matrix_version")
    observed_at = validate_string(manifest.get("observed_at"), "manifest.observed_at")
    expected_categories = manifest.get("expected_categories")
    expected_counts = manifest.get("expected_counts")
    require(isinstance(expected_categories, list) and len(expected_categories) == 7, "manifest must define 7 expected categories")
    require(isinstance(expected_counts, dict), "manifest.expected_counts must be an object")

    source_catalog_path = ROOT / validate_string(manifest.get("source_catalog"), "manifest.source_catalog")
    source_catalog = load_json(source_catalog_path)
    require(source_catalog.get("matrix_version") == matrix_version, "source catalog matrix_version mismatch")
    sources_raw = source_catalog.get("sources")
    require(isinstance(sources_raw, list) and sources_raw, "source catalog must contain sources")

    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources_raw):
        require(isinstance(source, dict), f"source[{index}] must be an object")
        source_id = validate_string(source.get("source_id"), f"source[{index}].source_id")
        require(source_id not in sources, f"duplicate source_id: {source_id}")
        require(validate_string(source.get("observed_at"), f"source[{source_id}].observed_at") <= observed_at, f"source {source_id} observed_at exceeds manifest")
        url = validate_string(source.get("url"), f"source[{source_id}].url")
        require(url.startswith("https://www.lovart.ai/"), f"source {source_id} must be an official lovart.ai URL")
        tier = source.get("tier")
        require(tier in {1, 2, 3}, f"source {source_id} tier must be 1, 2, or 3")
        sources[source_id] = source

    capability_glob = validate_string(manifest.get("capability_glob"), "manifest.capability_glob")
    capability_files = sorted(ROOT.glob(capability_glob))
    require(len(capability_files) == 7, f"expected 7 capability files, found {len(capability_files)}")

    capabilities: dict[str, dict[str, Any]] = {}
    categories_seen: set[str] = set()
    target_counts: Counter[str] = Counter()
    competitor_counts: Counter[str] = Counter()

    for path in capability_files:
        doc = load_json(path)
        require(doc.get("matrix_version") == matrix_version, f"{path.name}: matrix_version mismatch")
        require(doc.get("observed_at") == observed_at, f"{path.name}: observed_at mismatch")
        category = validate_string(doc.get("category"), f"{path.name}.category")
        require(category in expected_categories, f"{path.name}: unexpected category {category}")
        require(category not in categories_seen, f"duplicate category file: {category}")
        categories_seen.add(category)
        rows = doc.get("capabilities")
        require(isinstance(rows, list) and rows, f"{path.name}: capabilities must be a non-empty list")

        for row in rows:
            require(isinstance(row, dict), f"{path.name}: capability row must be an object")
            capability_id = validate_string(row.get("capability_id"), f"{path.name}.capability_id")
            require(CAPABILITY_RE.fullmatch(capability_id) is not None, f"invalid capability_id: {capability_id}")
            require(capability_id not in capabilities, f"duplicate capability_id: {capability_id}")
            require(row.get("category") == category, f"{capability_id}: category mismatch")
            validate_string(row.get("name"), f"{capability_id}.name")
            require(row.get("observed_at") == observed_at, f"{capability_id}: observed_at mismatch")

            competitor_status = validate_string(row.get("competitor_status"), f"{capability_id}.competitor_status")
            require(competitor_status in ALLOWED_COMPETITOR_STATUS, f"{capability_id}: invalid competitor_status")
            competitor_counts[competitor_status] += 1

            lumi_target = validate_string(row.get("lumi_target"), f"{capability_id}.lumi_target")
            require(lumi_target in ALLOWED_TARGETS, f"{capability_id}: invalid lumi_target")
            target_counts[lumi_target] += 1

            lumi_status = validate_string(row.get("lumi_status"), f"{capability_id}.lumi_status")
            require(lumi_status in ALLOWED_LUMI_STATUS, f"{capability_id}: invalid lumi_status")
            validate_string(row.get("gap"), f"{capability_id}.gap")

            owning_nodes = row.get("owning_nodes")
            require(isinstance(owning_nodes, list) and owning_nodes, f"{capability_id}: owning_nodes required")
            for node in owning_nodes:
                require(isinstance(node, str) and NODE_RE.fullmatch(node), f"{capability_id}: invalid owning node {node!r}")
            require(len(set(owning_nodes)) == len(owning_nodes), f"{capability_id}: duplicate owning nodes")

            evidence = row.get("evidence")
            require(isinstance(evidence, list), f"{capability_id}: evidence must be a list")
            if competitor_status == "not_confirmed":
                require(not evidence, f"{capability_id}: not_confirmed capability must not carry positive evidence")
            else:
                require(evidence, f"{capability_id}: confirmed capability requires evidence")
            for evidence_item in evidence:
                require(isinstance(evidence_item, dict), f"{capability_id}: evidence entry must be an object")
                source_id = validate_string(evidence_item.get("source_id"), f"{capability_id}.evidence.source_id")
                require(source_id in sources, f"{capability_id}: unknown source_id {source_id}")

            acceptance_case = row.get("acceptance_case")
            if lumi_target == "PARITY":
                require(isinstance(acceptance_case, str) and CASE_RE.fullmatch(acceptance_case), f"{capability_id}: PARITY requires a PARITY-XX acceptance_case")
                require(acceptance_case == f"PARITY-{capability_id}", f"{capability_id}: acceptance case must be PARITY-{capability_id}")
            else:
                require(acceptance_case is None, f"{capability_id}: only PARITY items may bind product-parity acceptance cases")

            capabilities[capability_id] = row

    require(categories_seen == set(expected_categories), "capability category coverage mismatch")

    acceptance_glob = validate_string(manifest.get("acceptance_glob"), "manifest.acceptance_glob")
    acceptance_files = sorted(ROOT.glob(acceptance_glob))
    require(len(acceptance_files) == 7, f"expected 7 acceptance files, found {len(acceptance_files)}")

    cases: dict[str, dict[str, Any]] = {}
    acceptance_categories: set[str] = set()
    for path in acceptance_files:
        doc = load_json(path)
        require(doc.get("dataset_version") == matrix_version, f"{path.name}: dataset_version mismatch")
        require(doc.get("observed_at") == observed_at, f"{path.name}: observed_at mismatch")
        category = validate_string(doc.get("category"), f"{path.name}.category")
        require(category in expected_categories, f"{path.name}: unexpected category")
        require(category not in acceptance_categories, f"duplicate acceptance category file: {category}")
        acceptance_categories.add(category)
        rows = doc.get("cases")
        require(isinstance(rows, list), f"{path.name}: cases must be a list")

        for case in rows:
            require(isinstance(case, dict), f"{path.name}: case must be an object")
            case_id = validate_string(case.get("case_id"), f"{path.name}.case_id")
            require(CASE_RE.fullmatch(case_id) is not None, f"invalid case_id: {case_id}")
            require(case_id not in cases, f"duplicate case_id: {case_id}")
            capability_id = validate_string(case.get("capability_id"), f"{case_id}.capability_id")
            require(capability_id in capabilities, f"{case_id}: unknown capability_id {capability_id}")
            capability = capabilities[capability_id]
            require(capability["lumi_target"] == "PARITY", f"{case_id}: only PARITY capabilities may have product-parity cases")
            require(capability["acceptance_case"] == case_id, f"{case_id}: capability acceptance_case mismatch")
            require(case.get("category") == capability["category"] == category, f"{case_id}: category mismatch")
            require(case.get("version") == 1, f"{case_id}: version must be 1 for matrix v1")
            validate_string(case.get("fixture"), f"{case_id}.fixture")
            validate_string(case.get("command"), f"{case_id}.command")
            expected = case.get("expected")
            require(isinstance(expected, list) and expected and all(isinstance(item, str) and item for item in expected), f"{case_id}: expected must be non-empty string list")
            validate_string(case.get("future_suite"), f"{case_id}.future_suite")
            require(case.get("status") == "SPECIFIED_NOT_RUN", f"{case_id}: NODE-06 cases must be SPECIFIED_NOT_RUN")
            require(set(case.get("owning_nodes", [])) == set(capability["owning_nodes"]), f"{case_id}: owning_nodes must match capability")
            cases[case_id] = case

    require(acceptance_categories == set(expected_categories), "acceptance category coverage mismatch")

    parity_capabilities = {capability_id for capability_id, row in capabilities.items() if row["lumi_target"] == "PARITY"}
    parity_case_capabilities = {case["capability_id"] for case in cases.values()}
    require(parity_capabilities == parity_case_capabilities, "PARITY capability/case coverage mismatch")

    expected_capabilities = expected_counts.get("capabilities")
    require(len(capabilities) == expected_capabilities, f"capability count mismatch: expected {expected_capabilities}, got {len(capabilities)}")
    expected_targets = expected_counts.get("targets")
    require(isinstance(expected_targets, dict), "manifest expected target counts missing")
    for target in ALLOWED_TARGETS:
        require(target_counts[target] == expected_targets.get(target, 0), f"target count mismatch for {target}: expected {expected_targets.get(target, 0)}, got {target_counts[target]}")
    expected_competitor = expected_counts.get("competitor_status")
    require(isinstance(expected_competitor, dict), "manifest expected competitor status counts missing")
    for status in ALLOWED_COMPETITOR_STATUS:
        require(competitor_counts[status] == expected_competitor.get(status, 0), f"competitor_status count mismatch for {status}: expected {expected_competitor.get(status, 0)}, got {competitor_counts[status]}")
    require(len(cases) == expected_counts.get("parity_acceptance_cases"), f"acceptance case count mismatch: expected {expected_counts.get('parity_acceptance_cases')}, got {len(cases)}")

    print(f"PASS product parity matrix v{matrix_version}")
    print(f"PASS categories={len(categories_seen)} capabilities={len(capabilities)} sources={len(sources)}")
    print("PASS targets=" + ", ".join(f"{target}:{target_counts[target]}" for target in ["PARITY", "SUPERSET", "DEFER", "OUT-OF-SCOPE"]))
    print("PASS competitor_status=" + ", ".join(f"{status}:{competitor_counts[status]}" for status in ["confirmed", "confirmed_marketing", "not_confirmed"]))
    print(f"PASS parity_acceptance_cases={len(cases)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"FAIL product parity contract: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
