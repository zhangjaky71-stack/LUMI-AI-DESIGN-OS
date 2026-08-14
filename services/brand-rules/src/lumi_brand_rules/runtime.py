from __future__ import annotations

from typing import Any, Mapping

from .model import (
    BrandAssetSet,
    BrandComplianceReport,
    BrandDiagnostic,
    BrandRule,
    BrandRuleError,
    BrandRuleSet,
    BrandTokenSet,
    validate_rule_set,
)


def _value(node: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = node
        for key in path.split("."):
            if not isinstance(current, Mapping):
                current = None
                break
            current = current.get(key)
        if current is not None:
            return current
    return None


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _applies(rule: BrandRule, node: Mapping[str, Any], channel: str | None, locale: str | None) -> bool:
    node_ids = _string_list(rule.scope.get("node_ids"))
    roles = _string_list(rule.scope.get("roles"))
    channels = _string_list(rule.scope.get("channels"))
    locales = _string_list(rule.scope.get("locales"))
    if node_ids and node.get("id") not in node_ids:
        return False
    if roles and node.get("role") not in roles:
        return False
    if channels and channel not in channels:
        return False
    return not locales or locale in locales


def _repair(document: Mapping[str, Any], node_id: str, path: str, value: Any, rule_id: str) -> Mapping[str, Any]:
    metadata = document.get("metadata", {})
    version = metadata.get("document_version", 0) if isinstance(metadata, Mapping) else 0
    return {
        "operation_id": f"brand-fix:{rule_id}:{node_id}:{path}",
        "type": "SET_PROPERTY",
        "target_ids": [node_id],
        "expected_document_version": version if isinstance(version, int) else 0,
        "payload": {"path": path, "value": value},
        "reason": f"BRAND_RULE_AUTO_FIX:{rule_id}",
    }


def _diag(
    rule: BrandRule,
    reason: str,
    node_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    repairs: tuple[Mapping[str, Any], ...] = (),
) -> BrandDiagnostic:
    return BrandDiagnostic(
        rule_id=rule.id,
        severity=rule.severity,
        category=rule.category,
        reason_code=reason,
        node_id=node_id,
        expected=expected,
        actual=actual,
        repair_operations=repairs,
    )


def _rect(node: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    transform = node.get("transform")
    if not isinstance(transform, Mapping):
        return None
    values = tuple(transform.get(key) for key in ("x", "y", "width", "height"))
    if not all(isinstance(value, (int, float)) for value in values):
        return None
    return tuple(float(value) for value in values)  # type: ignore[arg-type,return-value]


def _overlap_margin(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    margin: float,
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        bx >= ax + aw + margin
        or bx + bw <= ax - margin
        or by >= ay + ah + margin
        or by + bh <= ay - margin
    )


def _evaluate_rule(
    rule: BrandRule,
    document: Mapping[str, Any],
    token_set: BrandTokenSet,
    verified_asset_ids: frozenset[str] | None,
    font_rights_ids: frozenset[str] | None,
    channel: str | None,
    locale: str | None,
) -> list[BrandDiagnostic]:
    if not rule.active:
        return []
    nodes_raw = document.get("nodes", {})
    if not isinstance(nodes_raw, Mapping):
        return []
    nodes = [node for node in nodes_raw.values() if isinstance(node, Mapping)]
    nodes.sort(key=lambda item: str(item.get("id", "")))
    diagnostics: list[BrandDiagnostic] = []

    for node in nodes:
        if not _applies(rule, node, channel, locale):
            continue
        node_id = str(node.get("id", ""))
        if rule.type == "FORBIDDEN_COLORS":
            color = _value(node, "fill", "color", "style.fill", "metadata.fill")
            forbidden = {item.lower() for item in _string_list(rule.parameters.get("colors"))}
            if isinstance(color, str) and color.lower() in forbidden:
                replacement = next(iter(token_set.colors.values()), None)
                repairs = (
                    _repair(document, node_id, "fill", replacement, rule.id),
                ) if replacement else ()
                diagnostics.append(_diag(rule, "BRAND_COLOR_FORBIDDEN", node_id, sorted(forbidden), color, repairs))

        elif rule.type == "ALLOWED_FONT_ASSETS" and node.get("kind") == "TEXT":
            font_id = _value(node, "font_asset_id", "typography.font_asset_id", "metadata.font_asset_id")
            allowed = _string_list(rule.parameters.get("asset_ids"))
            rights_denied = isinstance(font_id, str) and font_rights_ids is not None and font_id not in font_rights_ids
            if not isinstance(font_id, str) or font_id not in allowed or rights_denied:
                replacement = next((item for item in allowed if font_rights_ids is None or item in font_rights_ids), None)
                repairs = (
                    _repair(document, node_id, "font_asset_id", replacement, rule.id),
                ) if replacement else ()
                diagnostics.append(_diag(
                    rule,
                    "BRAND_FONT_RIGHTS_UNAVAILABLE" if rights_denied else "BRAND_FONT_NOT_ALLOWED",
                    node_id,
                    allowed,
                    font_id,
                    repairs,
                ))

        elif rule.type == "MIN_TEXT_SIZE" and node.get("kind") == "TEXT":
            size = _value(node, "font_size", "typography.font_size", "metadata.font_size")
            minimum = rule.parameters.get("px", 0)
            if isinstance(size, (int, float)) and isinstance(minimum, (int, float)) and size < minimum:
                diagnostics.append(_diag(
                    rule,
                    "BRAND_TEXT_TOO_SMALL",
                    node_id,
                    minimum,
                    size,
                    (_repair(document, node_id, "font_size", minimum, rule.id),),
                ))

        elif rule.type == "REQUIRE_TOKEN_BINDING":
            binding = _value(node, "brand_binding", "metadata.brand_binding")
            prefixes = _string_list(rule.parameters.get("prefixes"))
            valid = isinstance(binding, str) and (not prefixes or any(binding.startswith(item) for item in prefixes))
            if not valid:
                repairs = (
                    _repair(document, node_id, "brand_binding", prefixes[0], rule.id),
                ) if prefixes else ()
                diagnostics.append(_diag(rule, "BRAND_TOKEN_BINDING_REQUIRED", node_id, prefixes, binding, repairs))

        elif rule.type == "LOGO_FORBID_ROTATION":
            rotation = _value(node, "transform.rotation_deg") or 0
            tolerance = rule.parameters.get("tolerance_deg", 0.01)
            if isinstance(rotation, (int, float)) and isinstance(tolerance, (int, float)) and abs(rotation) > tolerance:
                diagnostics.append(_diag(
                    rule,
                    "BRAND_LOGO_ROTATED",
                    node_id,
                    0,
                    rotation,
                    (_repair(document, node_id, "transform.rotation_deg", 0, rule.id),),
                ))

        elif rule.type == "LOGO_CLEAR_SPACE":
            bounds = _rect(node)
            margin = rule.parameters.get("px", 0)
            if bounds and isinstance(margin, (int, float)) and margin > 0:
                for other in nodes:
                    if other is node or other.get("visible") is False or other.get("kind") == "GUIDE":
                        continue
                    other_bounds = _rect(other)
                    if other_bounds and _overlap_margin(bounds, other_bounds, float(margin)):
                        diagnostics.append(_diag(
                            rule,
                            "BRAND_LOGO_CLEAR_SPACE_VIOLATION",
                            node_id,
                            margin,
                            other.get("id"),
                        ))
                        break

        elif rule.type in {"ALLOWED_ASSETS", "ALLOWED_LOGO_ASSETS"}:
            asset_id = _value(node, "asset_id", "resource_id", "metadata.asset_id")
            allowed = _string_list(rule.parameters.get("asset_ids"))
            if not isinstance(asset_id, str) or asset_id not in allowed:
                diagnostics.append(_diag(rule, "BRAND_ASSET_NOT_ALLOWED", node_id, allowed, asset_id))
            elif verified_asset_ids is not None and asset_id not in verified_asset_ids:
                diagnostics.append(_diag(rule, "BRAND_ASSET_NOT_VERIFIED", node_id, True, asset_id))

        elif rule.type == "VOICE_FORBIDDEN_TERMS" and node.get("kind") == "TEXT":
            text = _value(node, "text", "content", "metadata.text")
            terms = _string_list(rule.parameters.get("terms"))
            if isinstance(text, str):
                hit = next((term for term in terms if term.lower() in text.lower()), None)
                if hit:
                    diagnostics.append(_diag(rule, "BRAND_VOICE_FORBIDDEN_TERM", node_id, terms, hit))

    return diagnostics


def evaluate_brand_compliance(
    document: Mapping[str, Any],
    rule_set: BrandRuleSet,
    token_set: BrandTokenSet,
    asset_set: BrandAssetSet,
    *,
    verified_asset_ids: frozenset[str] | None = None,
    font_rights_allowed_asset_ids: frozenset[str] | None = None,
    channel: str | None = None,
    locale: str | None = None,
) -> BrandComplianceReport:
    validate_rule_set(rule_set)
    if rule_set.status != "PUBLISHED":
        raise BrandRuleError("compliance requires a PUBLISHED BrandRuleSet")
    if token_set.version != rule_set.token_set_version or asset_set.version != rule_set.asset_set_version:
        raise BrandRuleError("brand dependency version mismatch")
    if token_set.brand_profile_id != rule_set.brand_profile_id or asset_set.brand_profile_id != rule_set.brand_profile_id:
        raise BrandRuleError("brand profile mismatch")

    diagnostics: list[BrandDiagnostic] = []
    for rule in sorted(rule_set.rules, key=lambda item: (-item.priority, item.id)):
        diagnostics.extend(_evaluate_rule(
            rule,
            document,
            token_set,
            verified_asset_ids,
            font_rights_allowed_asset_ids,
            channel,
            locale,
        ))
    hard = sum(item.severity == "HARD" for item in diagnostics)
    soft = sum(item.severity == "SOFT" for item in diagnostics)
    advisory = sum(item.severity == "ADVISORY" for item in diagnostics)
    decision = "FAIL" if hard else "PASS_WITH_WARNINGS" if diagnostics else "PASS"
    return BrandComplianceReport(
        brand_rule_set_version=rule_set.version,
        decision=decision,
        score=max(0.0, min(1.0, 1 - hard * 0.25 - soft * 0.08 - advisory * 0.02)),
        diagnostics=tuple(diagnostics),
        hard_violation_count=hard,
        soft_violation_count=soft,
        advisory_count=advisory,
    )
