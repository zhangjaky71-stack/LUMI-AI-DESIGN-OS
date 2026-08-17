from __future__ import annotations

from lumi_api.constraints.models import Constraint, ConstraintScope, ConstraintSet

from .contracts import BrandRule, BrandRuleSet, RuleKind

_TYPE_BY_RULE = {
    RuleKind.MIN_CONTRAST: "REQUIRE_CONTRAST",
    RuleKind.FONT_MIN_SIZE: "REQUIRE_TEXT_READABILITY",
    RuleKind.LOGO_TRANSFORM: "LOCK_BRAND",
}


def _validator_parameters(rule: BrandRule) -> dict:
    params = dict(rule.parameters)
    if rule.kind == RuleKind.ALLOWED_COLOR:
        params["allowed_colors"] = tuple(rule.parameters.get("colors", ()))
    elif rule.kind == RuleKind.FONT_ALLOWED:
        params["allowed_fonts"] = tuple(rule.parameters.get("families", ()))
    elif rule.kind == RuleKind.MIN_CONTRAST:
        params["min_ratio"] = float(rule.parameters.get("ratio", 4.5))
    elif rule.kind == RuleKind.FONT_MIN_SIZE:
        params["min_font_size"] = float(rule.parameters.get("minimum", 12))
    elif rule.kind == RuleKind.LOGO_TRANSFORM:
        params["logo_rotation_forbidden"] = bool(
            rule.parameters.get("forbid_rotation", True)
        )
    return params


def compile_brand_constraints(rule_set: BrandRuleSet) -> ConstraintSet:
    constraints = []
    for rule in rule_set.rules:
        constraint_type = _TYPE_BY_RULE.get(rule.kind, "REQUIRE_BRAND_COMPLIANCE")
        constraints.append(
            Constraint(
                id=rule.id,
                type=constraint_type,
                scope=ConstraintScope(),
                severity=rule.severity.value,
                source="APPROVED_BRAND_RULE",
                priority=500,
                parameters={
                    "brand_rule_set_id": str(rule_set.id),
                    "brand_rule_set_version": rule_set.version,
                    "brand_rule_key": rule.key,
                    "brand_rule_kind": rule.kind.value,
                    **_validator_parameters(rule),
                },
            )
        )
    return ConstraintSet(constraints=tuple(constraints))
