from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    AssetRightsSnapshot,
    BrandObservation,
    BrandRule,
    BrandRuleSet,
    BrandViolation,
    ComplianceResult,
    RuleKind,
    RuleSeverity,
)
from .ports import AssetRightsReader

_WEIGHTS = {
    RuleSeverity.HARD: 5,
    RuleSeverity.SOFT: 2,
    RuleSeverity.ADVISORY: 1,
}


def _values(rule: BrandRule, key: str) -> set[str]:
    raw = rule.parameters.get(key, ())
    if isinstance(raw, str):
        return {raw.lower()}
    if isinstance(raw, (tuple, list, set)):
        return {str(item).lower() for item in raw}
    return set()


def _violation(
    rule: BrandRule,
    observation: BrandObservation,
    code: str,
    *,
    expected: dict | None = None,
    actual: dict | None = None,
    unavailable: bool = False,
) -> BrandViolation:
    return BrandViolation(
        rule_id=rule.id,
        rule_key=rule.key,
        severity=rule.severity,
        node_id=observation.node_id,
        code=code,
        expected=expected or {},
        actual=actual or {},
        unavailable=unavailable,
    )


def evaluate_observation(
    rule: BrandRule,
    observation: BrandObservation,
    rights: AssetRightsReader | None = None,
    organization_id=None,
) -> BrandViolation | None:
    if rule.kind == RuleKind.TOKEN_BINDING:
        required = bool(rule.parameters.get("required", True))
        allowed = _values(rule, "token_ids")
        binding = observation.brand_binding
        if required and not binding:
            return _violation(rule, observation, "BRAND_TOKEN_BINDING_REQUIRED")
        if binding and allowed and binding.lower() not in allowed:
            return _violation(
                rule,
                observation,
                "BRAND_TOKEN_BINDING_INVALID",
                expected={"token_ids": sorted(allowed)},
                actual={"brand_binding": binding},
            )

    elif rule.kind == RuleKind.FORBIDDEN_COLOR and observation.color:
        forbidden = _values(rule, "colors")
        if observation.color.lower() in forbidden:
            return _violation(
                rule,
                observation,
                "BRAND_FORBIDDEN_COLOR",
                expected={"forbidden": sorted(forbidden)},
                actual={"color": observation.color},
            )

    elif rule.kind == RuleKind.ALLOWED_COLOR and observation.color:
        allowed = _values(rule, "colors")
        if allowed and observation.color.lower() not in allowed:
            return _violation(
                rule,
                observation,
                "BRAND_COLOR_NOT_ALLOWED",
                expected={"allowed": sorted(allowed)},
                actual={"color": observation.color},
            )

    elif rule.kind == RuleKind.MIN_CONTRAST:
        minimum = float(rule.parameters.get("ratio", 4.5))
        if observation.contrast_ratio is None:
            return _violation(
                rule,
                observation,
                "BRAND_CONTRAST_UNAVAILABLE",
                expected={"minimum_ratio": minimum},
                unavailable=True,
            )
        if observation.contrast_ratio < minimum:
            return _violation(
                rule,
                observation,
                "BRAND_CONTRAST_TOO_LOW",
                expected={"minimum_ratio": minimum},
                actual={"contrast_ratio": observation.contrast_ratio},
            )

    elif rule.kind == RuleKind.FONT_ALLOWED and (
        observation.font_asset_id is not None or observation.font_family is not None
    ):
        allowed_ids = {str(item) for item in rule.parameters.get("asset_ids", ())}
        allowed_families = _values(rule, "families")
        if observation.font_asset_id is not None and allowed_ids:
            if str(observation.font_asset_id) not in allowed_ids:
                return _violation(rule, observation, "BRAND_FONT_NOT_ALLOWED")
            if rights is not None:
                state: AssetRightsSnapshot = rights.read(
                    organization_id, observation.font_asset_id
                )
                if not state.exists or not state.ready or state.media_kind != "font":
                    return _violation(
                        rule,
                        observation,
                        "BRAND_FONT_UNAVAILABLE",
                        unavailable=True,
                    )
                if state.commercial_use is False:
                    return _violation(
                        rule,
                        observation,
                        "BRAND_FONT_RIGHTS_DENIED",
                    )
        elif observation.font_family and allowed_families:
            if observation.font_family.lower() not in allowed_families:
                return _violation(rule, observation, "BRAND_FONT_NOT_ALLOWED")

    elif rule.kind == RuleKind.FONT_MIN_SIZE and observation.kind.upper() == "TEXT":
        minimum = float(rule.parameters.get("minimum", 12))
        if observation.font_size is None:
            return _violation(
                rule, observation, "BRAND_FONT_SIZE_UNAVAILABLE", unavailable=True
            )
        if observation.font_size < minimum:
            return _violation(
                rule,
                observation,
                "BRAND_FONT_TOO_SMALL",
                expected={"minimum": minimum},
                actual={"font_size": observation.font_size},
            )

    elif rule.kind == RuleKind.LOGO_ALLOWED_ASSET and observation.kind.upper() == "LOGO":
        allowed = {str(item) for item in rule.parameters.get("asset_ids", ())}
        if observation.asset_id is None or (
            allowed and str(observation.asset_id) not in allowed
        ):
            return _violation(rule, observation, "BRAND_LOGO_ASSET_NOT_ALLOWED")

    elif rule.kind == RuleKind.LOGO_MIN_SIZE and observation.kind.upper() == "LOGO":
        min_w = float(rule.parameters.get("min_width", 0))
        min_h = float(rule.parameters.get("min_height", 0))
        if observation.width is None or observation.height is None:
            return _violation(
                rule, observation, "BRAND_LOGO_SIZE_UNAVAILABLE", unavailable=True
            )
        if observation.width < min_w or observation.height < min_h:
            return _violation(
                rule,
                observation,
                "BRAND_LOGO_TOO_SMALL",
                expected={"min_width": min_w, "min_height": min_h},
                actual={"width": observation.width, "height": observation.height},
            )

    elif rule.kind == RuleKind.LOGO_CLEAR_SPACE and observation.kind.upper() == "LOGO":
        minimum = float(rule.parameters.get("minimum", 0))
        if observation.clear_space is None:
            return _violation(
                rule, observation, "BRAND_LOGO_CLEAR_SPACE_UNAVAILABLE", unavailable=True
            )
        if observation.clear_space < minimum:
            return _violation(
                rule,
                observation,
                "BRAND_LOGO_CLEAR_SPACE",
                expected={"minimum": minimum},
                actual={"clear_space": observation.clear_space},
            )

    elif rule.kind == RuleKind.LOGO_TRANSFORM and observation.kind.upper() == "LOGO":
        forbid_rotation = bool(rule.parameters.get("forbid_rotation", True))
        forbid_stretch = bool(rule.parameters.get("forbid_stretch", True))
        forbid_recolor = bool(rule.parameters.get("forbid_recolor", True))
        if forbid_rotation and abs(observation.rotation_deg or 0) > 1e-6:
            return _violation(rule, observation, "BRAND_LOGO_ROTATED")
        if forbid_stretch:
            sx = observation.scale_x
            sy = observation.scale_y
            if sx is not None and sy is not None and abs(sx - sy) > 1e-6:
                return _violation(rule, observation, "BRAND_LOGO_STRETCHED")
        if forbid_recolor and observation.recolored:
            return _violation(rule, observation, "BRAND_LOGO_RECOLORED")

    return None


def evaluate_compliance(
    organization_id,
    rule_set: BrandRuleSet,
    observations: Iterable[BrandObservation],
    rights: AssetRightsReader | None = None,
) -> ComplianceResult:
    violations: list[BrandViolation] = []
    observations = tuple(observations)
    for rule in rule_set.rules:
        if rule.kind in {RuleKind.COPY_VOCABULARY, RuleKind.VISUAL_STYLE}:
            continue
        for observation in observations:
            issue = evaluate_observation(
                rule, observation, rights=rights, organization_id=organization_id
            )
            if issue is not None:
                violations.append(issue)

    weighted = sum(_WEIGHTS[item.severity] for item in violations)
    denominator = max(1, sum(_WEIGHTS[item.severity] for item in rule_set.rules))
    score = max(0.0, 100.0 * (1.0 - min(1.0, weighted / denominator)))
    can_approve = not any(item.blocking for item in violations)
    return ComplianceResult(
        rule_set_id=rule_set.id,
        rule_set_version=rule_set.version,
        violations=tuple(violations),
        score=round(score, 4),
        can_approve=can_approve,
    )
