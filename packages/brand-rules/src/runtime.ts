import { getDocumentVersion } from "../../design-ir/src/index";
import type { DesignNode, DesignOperation, JsonValue } from "../../design-ir/src/index";
import type {
  BrandAssetSet,
  BrandComplianceReport,
  BrandDiagnostic,
  BrandEvaluationContext,
  BrandRule,
  BrandRuleSet,
  BrandTokenSet,
} from "./types";

export class BrandRuleError extends Error {}

function stringArray(value: JsonValue | undefined): readonly string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function numberValue(value: JsonValue | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function rawNode(node: DesignNode): Readonly<Record<string, unknown>> {
  return node as unknown as Readonly<Record<string, unknown>>;
}

function nested(node: DesignNode, path: string): unknown {
  let current: unknown = rawNode(node);
  for (const key of path.split(".")) {
    if (current === null || typeof current !== "object" || Array.isArray(current)) return undefined;
    current = (current as Readonly<Record<string, unknown>>)[key];
  }
  return current;
}

function firstString(node: DesignNode, paths: readonly string[]): string | undefined {
  for (const path of paths) {
    const value = nested(node, path);
    if (typeof value === "string" && value) return value;
  }
  return undefined;
}

function normalizedColor(value: string): string {
  return value.trim().toLowerCase();
}

function nodeColor(node: DesignNode): string | undefined {
  return firstString(node, ["fill", "color", "background_color", "style.fill", "metadata.fill"]);
}

function nodeAssetId(node: DesignNode): string | undefined {
  return firstString(node, ["asset_id", "resource_id", "metadata.asset_id", "metadata.resource_id"]);
}

function nodeFontAssetId(node: DesignNode): string | undefined {
  return firstString(node, ["font_asset_id", "typography.font_asset_id", "metadata.font_asset_id"]);
}

function nodeText(node: DesignNode): string | undefined {
  return firstString(node, ["text", "content", "metadata.text"]);
}

function nodeBrandBinding(node: DesignNode): string | undefined {
  return firstString(node, ["brand_binding", "metadata.brand_binding"]);
}

function appliesToRule(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): boolean {
  const { scope } = rule;
  if (scope.node_ids?.length && !scope.node_ids.includes(node.id)) return false;
  if (scope.roles?.length && (!node.role || !scope.roles.includes(node.role))) return false;
  if (scope.channels?.length && (!context.channel || !scope.channels.includes(context.channel))) return false;
  if (scope.locales?.length && (!context.locale || !scope.locales.includes(context.locale))) return false;
  return true;
}

function repairOperation(
  context: BrandEvaluationContext,
  nodeId: string,
  path: string,
  value: unknown,
  ruleId: string,
): DesignOperation {
  return {
    operation_id: `brand-fix:${ruleId}:${nodeId}:${path}`,
    type: "SET_PROPERTY",
    target_ids: [nodeId],
    expected_document_version: getDocumentVersion(context.document),
    payload: { path, value },
    reason: `BRAND_RULE_AUTO_FIX:${ruleId}`,
  };
}

function diagnostic(
  rule: BrandRule,
  reasonCode: string,
  nodeId?: string,
  expected?: JsonValue,
  actual?: JsonValue,
  repairOperations?: readonly DesignOperation[],
): BrandDiagnostic {
  return {
    rule_id: rule.id,
    severity: rule.severity,
    category: rule.category,
    reason_code: reasonCode,
    ...(nodeId ? { node_id: nodeId } : {}),
    ...(expected !== undefined ? { expected } : {}),
    ...(actual !== undefined ? { actual } : {}),
    ...(repairOperations?.length ? { repair_operations: repairOperations } : {}),
  };
}

function tokenColorMap(tokenSet: BrandTokenSet): Map<string, string> {
  return new Map(tokenSet.colors.map((token) => [token.id, normalizedColor(token.value)]));
}

function evaluateColor(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): BrandDiagnostic[] {
  const color = nodeColor(node);
  if (!color) return [];
  const normalized = normalizedColor(color);
  const tokenColors = tokenColorMap(context.token_set);

  if (rule.type === "ALLOWED_COLOR_TOKENS") {
    const tokenIds = stringArray(rule.parameters.token_ids);
    const allowed = new Set(tokenIds.map((id) => tokenColors.get(id)).filter((item): item is string => Boolean(item)));
    if (!allowed.size || allowed.has(normalized)) return [];
    const replacementToken = tokenIds.find((id) => tokenColors.has(id));
    const replacement = replacementToken ? tokenColors.get(replacementToken) : undefined;
    return [diagnostic(
      rule,
      "BRAND_COLOR_NOT_ALLOWED",
      node.id,
      tokenIds,
      color,
      replacement ? [repairOperation(context, node.id, "fill", replacement, rule.id)] : undefined,
    )];
  }

  if (rule.type === "FORBIDDEN_COLORS") {
    const forbidden = new Set(stringArray(rule.parameters.colors).map(normalizedColor));
    if (!forbidden.has(normalized)) return [];
    const replacement = context.token_set.colors[0]?.value;
    return [diagnostic(
      rule,
      "BRAND_COLOR_FORBIDDEN",
      node.id,
      stringArray(rule.parameters.colors),
      color,
      replacement ? [repairOperation(context, node.id, "fill", replacement, rule.id)] : undefined,
    )];
  }
  return [];
}

function evaluateTypography(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): BrandDiagnostic[] {
  if (node.kind !== "TEXT") return [];
  if (rule.type === "ALLOWED_FONT_ASSETS") {
    const assetId = nodeFontAssetId(node);
    const allowed = new Set(stringArray(rule.parameters.asset_ids));
    if (!assetId || !allowed.has(assetId)) {
      const replacement = [...allowed].find((id) => context.font_rights_allowed_asset_ids?.includes(id) ?? true);
      return [diagnostic(
        rule,
        assetId && !context.font_rights_allowed_asset_ids?.includes(assetId)
          ? "BRAND_FONT_RIGHTS_UNAVAILABLE"
          : "BRAND_FONT_NOT_ALLOWED",
        node.id,
        [...allowed],
        assetId ?? null,
        replacement ? [repairOperation(context, node.id, "font_asset_id", replacement, rule.id)] : undefined,
      )];
    }
    if (context.font_rights_allowed_asset_ids && !context.font_rights_allowed_asset_ids.includes(assetId)) {
      return [diagnostic(rule, "BRAND_FONT_RIGHTS_UNAVAILABLE", node.id, [...allowed], assetId)];
    }
  }

  if (rule.type === "MIN_TEXT_SIZE") {
    const size = nested(node, "font_size") ?? nested(node, "typography.font_size") ?? nested(node, "metadata.font_size");
    const minimum = numberValue(rule.parameters.px, 0);
    if (typeof size === "number" && size < minimum) {
      return [diagnostic(
        rule,
        "BRAND_TEXT_TOO_SMALL",
        node.id,
        minimum,
        size,
        [repairOperation(context, node.id, "font_size", minimum, rule.id)],
      )];
    }
  }
  return [];
}

function rect(node: DesignNode): { x: number; y: number; width: number; height: number } | null {
  const transform = node.transform;
  if (!transform) return null;
  const { x, y, width, height } = transform;
  if (![x, y, width, height].every((value) => typeof value === "number" && Number.isFinite(value))) return null;
  return { x: x as number, y: y as number, width: width as number, height: height as number };
}

function overlapsWithMargin(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
  margin: number,
): boolean {
  return !(
    b.x >= a.x + a.width + margin ||
    b.x + b.width <= a.x - margin ||
    b.y >= a.y + a.height + margin ||
    b.y + b.height <= a.y - margin
  );
}

function evaluateLogo(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): BrandDiagnostic[] {
  const diagnostics: BrandDiagnostic[] = [];
  const assetId = nodeAssetId(node);
  if (rule.type === "ALLOWED_LOGO_ASSETS") {
    const allowed = new Set(stringArray(rule.parameters.asset_ids));
    if (!assetId || !allowed.has(assetId)) {
      diagnostics.push(diagnostic(rule, "BRAND_LOGO_ASSET_NOT_ALLOWED", node.id, [...allowed], assetId ?? null));
    }
  }
  if (rule.type === "LOGO_MIN_SIZE") {
    const bounds = rect(node);
    if (bounds) {
      const minWidth = numberValue(rule.parameters.min_width, 0);
      const minHeight = numberValue(rule.parameters.min_height, 0);
      if (bounds.width < minWidth || bounds.height < minHeight) {
        diagnostics.push(diagnostic(rule, "BRAND_LOGO_TOO_SMALL", node.id, { min_width: minWidth, min_height: minHeight }, { width: bounds.width, height: bounds.height }));
      }
    }
  }
  if (rule.type === "LOGO_FORBID_ROTATION") {
    const rotation = node.transform?.rotation_deg ?? 0;
    const tolerance = numberValue(rule.parameters.tolerance_deg, 0.01);
    if (Math.abs(rotation) > tolerance) {
      diagnostics.push(diagnostic(rule, "BRAND_LOGO_ROTATED", node.id, 0, rotation, [repairOperation(context, node.id, "transform.rotation_deg", 0, rule.id)]));
    }
  }
  if (rule.type === "LOGO_FORBID_STRETCH") {
    const sx = node.transform?.scale_x ?? 1;
    const sy = node.transform?.scale_y ?? 1;
    const tolerance = numberValue(rule.parameters.tolerance, 0.01);
    if (Math.abs(sx - sy) > tolerance) diagnostics.push(diagnostic(rule, "BRAND_LOGO_STRETCHED", node.id, "uniform-scale", { scale_x: sx, scale_y: sy }));
  }
  if (rule.type === "LOGO_FORBID_RECOLOR") {
    const recolored = nested(node, "metadata.logo_recolored");
    if (recolored === true) diagnostics.push(diagnostic(rule, "BRAND_LOGO_RECOLORED", node.id, false, true));
  }
  if (rule.type === "LOGO_CLEAR_SPACE") {
    const bounds = rect(node);
    const margin = numberValue(rule.parameters.px, 0);
    if (bounds && margin > 0) {
      for (const other of Object.values(context.document.nodes)) {
        if (other.id === node.id || other.visible === false || other.kind === "GUIDE") continue;
        const otherBounds = rect(other);
        if (otherBounds && overlapsWithMargin(bounds, otherBounds, margin)) {
          diagnostics.push(diagnostic(rule, "BRAND_LOGO_CLEAR_SPACE_VIOLATION", node.id, margin, other.id));
          break;
        }
      }
    }
  }
  return diagnostics;
}

function evaluateBinding(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): BrandDiagnostic[] {
  if (rule.type !== "REQUIRE_TOKEN_BINDING") return [];
  const binding = nodeBrandBinding(node);
  const prefixes = stringArray(rule.parameters.prefixes);
  if (binding && (!prefixes.length || prefixes.some((prefix) => binding.startsWith(prefix)))) return [];
  const suggested = prefixes[0];
  return [diagnostic(
    rule,
    "BRAND_TOKEN_BINDING_REQUIRED",
    node.id,
    prefixes,
    binding ?? null,
    suggested ? [repairOperation(context, node.id, "brand_binding", suggested, rule.id)] : undefined,
  )];
}

function evaluateAsset(rule: BrandRule, node: DesignNode, context: BrandEvaluationContext): BrandDiagnostic[] {
  if (rule.type !== "ALLOWED_ASSETS" || !["IMAGE", "VIDEO", "VECTOR_PATH"].includes(node.kind)) return [];
  const assetId = nodeAssetId(node);
  const allowed = new Set(stringArray(rule.parameters.asset_ids));
  if (!assetId || !allowed.has(assetId)) return [diagnostic(rule, "BRAND_ASSET_NOT_ALLOWED", node.id, [...allowed], assetId ?? null)];
  if (context.verified_asset_ids && !context.verified_asset_ids.includes(assetId)) return [diagnostic(rule, "BRAND_ASSET_NOT_VERIFIED", node.id, true, assetId)];
  return [];
}

function evaluateVoice(rule: BrandRule, node: DesignNode): BrandDiagnostic[] {
  if (node.kind !== "TEXT") return [];
  const text = nodeText(node);
  if (!text) return [];
  if (rule.type === "VOICE_FORBIDDEN_TERMS") {
    const forbidden = stringArray(rule.parameters.terms);
    const lowered = text.toLocaleLowerCase();
    const hit = forbidden.find((term) => lowered.includes(term.toLocaleLowerCase()));
    return hit ? [diagnostic(rule, "BRAND_VOICE_FORBIDDEN_TERM", node.id, forbidden, hit)] : [];
  }
  return [];
}

function evaluateRule(rule: BrandRule, context: BrandEvaluationContext): BrandDiagnostic[] {
  if (!rule.active) return [];
  const diagnostics: BrandDiagnostic[] = [];
  const nodes = Object.values(context.document.nodes).sort((a, b) => a.id.localeCompare(b.id));
  for (const node of nodes) {
    if (!appliesToRule(rule, node, context)) continue;
    diagnostics.push(...evaluateColor(rule, node, context));
    diagnostics.push(...evaluateTypography(rule, node, context));
    diagnostics.push(...evaluateLogo(rule, node, context));
    diagnostics.push(...evaluateBinding(rule, node, context));
    diagnostics.push(...evaluateAsset(rule, node, context));
    diagnostics.push(...evaluateVoice(rule, node));
  }
  return diagnostics;
}

export function validateBrandRuleSet(ruleSet: BrandRuleSet): void {
  if (!ruleSet.id || !ruleSet.brand_profile_id || !ruleSet.version) throw new BrandRuleError("brand rule set identity is required");
  if (new Set(ruleSet.rules.map((rule) => rule.id)).size !== ruleSet.rules.length) throw new BrandRuleError("brand rule ids must be unique");
  for (const rule of ruleSet.rules) {
    if (!Number.isFinite(rule.priority)) throw new BrandRuleError(`rule ${rule.id} priority must be finite`);
    if (rule.source === "INFERRED_PROPOSAL" && rule.severity === "HARD") {
      throw new BrandRuleError(`inferred proposal ${rule.id} cannot be HARD`);
    }
    if (rule.source === "APPROVED_GUIDE_EXTRACTION" && !rule.citations?.length) {
      throw new BrandRuleError(`approved guide rule ${rule.id} requires source citations`);
    }
  }
  if (ruleSet.status === "PUBLISHED" && ruleSet.rules.some((rule) => rule.source === "INFERRED_PROPOSAL")) {
    throw new BrandRuleError("published rule sets cannot contain unreviewed inferred proposals");
  }
}

export function publishBrandRuleSet(ruleSet: BrandRuleSet, publishedAt: string): BrandRuleSet {
  const candidate: BrandRuleSet = { ...ruleSet, status: "PUBLISHED", published_at: publishedAt };
  validateBrandRuleSet(candidate);
  return candidate;
}

export function evaluateBrandCompliance(context: BrandEvaluationContext): BrandComplianceReport {
  validateBrandRuleSet(context.rule_set);
  if (context.rule_set.status !== "PUBLISHED") throw new BrandRuleError("compliance requires a PUBLISHED BrandRuleSet");
  if (context.token_set.version !== context.rule_set.token_set_version) throw new BrandRuleError("token set version mismatch");
  if (context.asset_set.version !== context.rule_set.asset_set_version) throw new BrandRuleError("asset set version mismatch");

  const diagnostics = context.rule_set.rules
    .slice()
    .sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id))
    .flatMap((rule) => evaluateRule(rule, context));
  const hard = diagnostics.filter((item) => item.severity === "HARD").length;
  const soft = diagnostics.filter((item) => item.severity === "SOFT").length;
  const advisory = diagnostics.filter((item) => item.severity === "ADVISORY").length;
  const penalty = hard * 0.25 + soft * 0.08 + advisory * 0.02;
  return {
    brand_rule_set_version: context.rule_set.version,
    decision: hard > 0 ? "FAIL" : diagnostics.length > 0 ? "PASS_WITH_WARNINGS" : "PASS",
    score: Math.max(0, Math.min(1, 1 - penalty)),
    diagnostics,
    hard_violation_count: hard,
    soft_violation_count: soft,
    advisory_count: advisory,
  };
}
