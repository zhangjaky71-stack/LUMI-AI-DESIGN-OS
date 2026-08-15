import { LumiApiError } from "@/lib/app-shell/api-client";
import type { BrandKitDetail, SaveBrandDraftInput } from "./types";

export function brandKitProblem(code: string, status = 409): LumiApiError {
  return new LumiApiError({
    type: `https://errors.lumi.dev/brand-kit/${code.toLowerCase().replaceAll("_", "-")}`,
    title: code,
    status,
    code,
    request_id: `brand-kit-${code.toLowerCase()}`,
  });
}

export function normalizeHexColor(value: string): string | null {
  const compact = value.trim().toUpperCase();
  const short = /^#([0-9A-F]{3})$/.exec(compact);
  if (short?.[1]) {
    const [r, g, b] = short[1].split("");
    return `#${r}${r}${g}${g}${b}${b}`;
  }
  return /^#[0-9A-F]{6}$/.test(compact) ? compact : null;
}

function channel(value: string): number {
  const normalized = Number.parseInt(value, 16) / 255;
  return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
}

export function contrastRatio(foreground: string, background: string): number | null {
  const fg = normalizeHexColor(foreground);
  const bg = normalizeHexColor(background);
  if (!fg || !bg) return null;
  const luminance = (value: string) => {
    const r = channel(value.slice(1, 3));
    const g = channel(value.slice(3, 5));
    const b = channel(value.slice(5, 7));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export function duplicateColorTokenIds(
  input: SaveBrandDraftInput["token_set"],
): readonly string[] {
  const seen = new Map<string, string>();
  const duplicates: string[] = [];
  for (const color of input.colors) {
    const normalized = normalizeHexColor(color.value);
    if (!normalized) continue;
    const first = seen.get(normalized);
    if (first) {
      duplicates.push(first, color.id);
    } else {
      seen.set(normalized, color.id);
    }
  }
  return [...new Set(duplicates)];
}

export function draftPublishIssues(detail: BrandKitDetail): readonly string[] {
  const issues: string[] = [];
  if (!detail.profile.name.trim()) issues.push("品牌名称不能为空。");
  if (!detail.draft_token_set.colors.length) issues.push("至少需要一个品牌色 token。");
  if (detail.draft_token_set.colors.some((color) => !normalizeHexColor(color.value))) {
    issues.push("颜色 token 必须使用有效 HEX。");
  }
  if (duplicateColorTokenIds(detail.draft_token_set).length) {
    issues.push("存在重复颜色值，请合并或明确 token 角色。");
  }

  const activeLogoIds = new Set(detail.draft_asset_set.logo_asset_ids);
  const activeLogos = detail.logos.filter((asset) => activeLogoIds.has(asset.asset_id));
  if (activeLogos.some((asset) => asset.scan_status !== "READY")) {
    issues.push("BrandRuleSet 使用的 Logo 仍在扫描或已被拒绝，不能发布。");
  }

  const usedFontAssets = new Set(detail.draft_token_set.fonts.map((font) => font.asset_id));
  const relevantFonts = detail.fonts.filter((font) => usedFontAssets.has(font.asset_id));
  if (relevantFonts.some((font) => font.scan_status !== "READY")) {
    issues.push("被 BrandRuleSet 使用的字体尚未通过 Asset 验证。");
  }
  if (relevantFonts.some((font) => font.rights_assertion === "UNKNOWN")) {
    issues.push("被 BrandRuleSet 使用的字体存在 UNKNOWN 授权声明。");
  }
  if (
    detail.draft_rule_set.rules.some(
      (rule) => rule.source === "INFERRED_PROPOSAL" && rule.severity === "HARD",
    )
  ) {
    issues.push("未经人工审核的提取建议不能成为 HARD rule。");
  }
  if (
    detail.draft_rule_set.rules.some(
      (rule) => rule.source === "INFERRED_PROPOSAL" && rule.active,
    )
  ) {
    issues.push("仍有未审核的 Brand Guide proposal rule，发布前必须审核。");
  }
  return issues;
}

export function validateSaveDraftInput(input: SaveBrandDraftInput): SaveBrandDraftInput {
  const name = input.name.trim();
  if (!name) throw brandKitProblem("BRAND_NAME_REQUIRED", 400);
  if (!Number.isSafeInteger(input.expected_draft_revision) || input.expected_draft_revision < 1) {
    throw brandKitProblem("DRAFT_REVISION_INVALID", 400);
  }
  for (const color of input.token_set.colors) {
    if (!normalizeHexColor(color.value)) throw brandKitProblem("COLOR_HEX_INVALID", 400);
  }
  return { ...input, name };
}
