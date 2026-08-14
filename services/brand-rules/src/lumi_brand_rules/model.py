from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

Severity = Literal["HARD", "SOFT", "ADVISORY"]
Source = Literal["USER_EXPLICIT", "APPROVED_GUIDE_EXTRACTION", "MANUAL_ADMIN", "INFERRED_PROPOSAL"]
RuleSetStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]


@dataclass(frozen=True, slots=True)
class BrandRule:
    id: str
    category: str
    type: str
    severity: Severity
    source: Source
    priority: int
    scope: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    active: bool = True
    citations: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class BrandRuleSet:
    id: str
    organization_id: str
    brand_profile_id: str
    version: str
    status: RuleSetStatus
    token_set_version: str
    asset_set_version: str
    rules: tuple[BrandRule, ...]
    voice: Mapping[str, Any] = field(default_factory=dict)
    visual_references: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrandTokenSet:
    brand_profile_id: str
    version: str
    colors: Mapping[str, str]
    font_asset_ids: tuple[str, ...]
    spacing_scale: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class BrandAssetSet:
    brand_profile_id: str
    version: str
    logo_asset_ids: tuple[str, ...]
    font_asset_ids: tuple[str, ...]
    reference_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrandDiagnostic:
    rule_id: str
    severity: Severity
    category: str
    reason_code: str
    node_id: str | None = None
    expected: Any = None
    actual: Any = None
    repair_operations: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class BrandComplianceReport:
    brand_rule_set_version: str
    decision: Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]
    score: float
    diagnostics: tuple[BrandDiagnostic, ...]
    hard_violation_count: int
    soft_violation_count: int
    advisory_count: int


class BrandRuleError(ValueError):
    pass


def validate_rule_set(rule_set: BrandRuleSet) -> None:
    if not rule_set.id or not rule_set.organization_id or not rule_set.brand_profile_id or not rule_set.version:
        raise BrandRuleError("brand rule set identity is required")
    if len({rule.id for rule in rule_set.rules}) != len(rule_set.rules):
        raise BrandRuleError("brand rule ids must be unique")
    for rule in rule_set.rules:
        if rule.source == "INFERRED_PROPOSAL" and rule.severity == "HARD":
            raise BrandRuleError(f"inferred proposal {rule.id} cannot be HARD")
        if rule.source == "APPROVED_GUIDE_EXTRACTION" and not rule.citations:
            raise BrandRuleError(f"approved guide rule {rule.id} requires citations")
    if rule_set.status == "PUBLISHED" and any(rule.source == "INFERRED_PROPOSAL" for rule in rule_set.rules):
        raise BrandRuleError("published rule sets cannot contain inferred proposals")


def publish_rule_set(rule_set: BrandRuleSet) -> BrandRuleSet:
    candidate = replace(rule_set, status="PUBLISHED")
    validate_rule_set(candidate)
    return candidate
