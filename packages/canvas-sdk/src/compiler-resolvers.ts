import { canonicalStringify, type DesignDocument, type JsonValue } from "../../design-ir/src/index";
import type {
  CompilerAssetResolver,
  CompilerFontResolver,
  CompilerResourceVariant,
  CompilerStyleResolver,
  CompilerTextMeasurer,
  ResolvedCompilerFont,
  ResolvedCompilerResource,
  ResolvedCompilerStyle,
} from "./compiler-types";

function asRecord(value: JsonValue | undefined): Readonly<Record<string, JsonValue>> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  return value;
}

function stringValue(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function resourceUri(
  record: Readonly<Record<string, JsonValue>>,
  variant: CompilerResourceVariant,
): string | null {
  const variantKey = `${variant}_uri`;
  return stringValue(record[variantKey]) ?? stringValue(record.uri);
}

export class DocumentCompilerStyleResolver implements CompilerStyleResolver {
  resolveStyle(
    document: DesignDocument,
    styleRefs: readonly string[],
  ): { readonly style: ResolvedCompilerStyle; readonly missing_refs: readonly string[] } {
    const style: Record<string, JsonValue> = {};
    const missing: string[] = [];
    for (const ref of styleRefs) {
      const record = asRecord(document.resources[ref]);
      if (!record) {
        missing.push(ref);
        continue;
      }
      const token = asRecord(record.value) ?? asRecord(record.style) ?? record;
      for (const [key, value] of Object.entries(token)) {
        if (["uri", "preview_uri", "full_uri", "thumbnail_uri"].includes(key)) continue;
        style[key] = structuredClone(value);
      }
    }
    return { style, missing_refs: missing };
  }
}

/**
 * Deterministic fallback resolver for fixtures/offline compilation.
 * Production authorization can replace this resolver without changing Design IR.
 */
export class DocumentCompilerAssetResolver implements CompilerAssetResolver {
  async resolveAsset(
    document: DesignDocument,
    assetId: string,
    variant: CompilerResourceVariant,
  ): Promise<ResolvedCompilerResource | null> {
    const record = asRecord(document.resources[assetId]);
    if (!record) return null;
    const version = stringValue(record.version) ?? "unversioned";
    const uri = resourceUri(record, variant);
    const mime = stringValue(record.mime_type) ?? undefined;
    const width = numberValue(record.width) ?? undefined;
    const height = numberValue(record.height) ?? undefined;
    return {
      asset_id: assetId,
      variant,
      version,
      status: uri ? "READY" : "PENDING",
      fingerprint: canonicalStringify({ asset_id: assetId, variant, version }),
      ...(uri ? { uri } : {}),
      ...(mime ? { mime_type: mime } : {}),
      ...(width !== undefined ? { width } : {}),
      ...(height !== undefined ? { height } : {}),
    };
  }
}

export class DocumentCompilerFontResolver implements CompilerFontResolver {
  async resolveFont(
    document: DesignDocument,
    fontRef: string,
  ): Promise<ResolvedCompilerFont | null> {
    const record = asRecord(document.resources[fontRef]);
    if (!record) return null;
    const family = stringValue(record.family) ?? stringValue(record.name) ?? fontRef;
    const version = stringValue(record.version) ?? "unversioned";
    const uri = stringValue(record.uri) ?? undefined;
    const style = stringValue(record.style) ?? undefined;
    const weightValue = numberValue(record.weight);
    return {
      font_ref: fontRef,
      family,
      version,
      status: uri ? "READY" : "PENDING",
      fingerprint: canonicalStringify({ font_ref: fontRef, family, version, style, weight: weightValue }),
      ...(uri ? { uri } : {}),
      ...(style ? { style } : {}),
      ...(weightValue !== null ? { weight: weightValue } : {}),
    };
  }
}

/**
 * Server/export may inject a real deterministic font shaper. This fallback intentionally avoids
 * browser DOM metrics and derives stable fixture dimensions from compiler inputs.
 */
export class DeterministicTextMeasurer implements CompilerTextMeasurer {
  async measure(
    content: string,
    style: ResolvedCompilerStyle,
    font: ResolvedCompilerFont | null,
  ): Promise<{ readonly width: number; readonly height: number; readonly baseline: number }> {
    const fontSizeValue = style.font_size;
    const fontSize = typeof fontSizeValue === "number" && Number.isFinite(fontSizeValue)
      ? Math.max(1, fontSizeValue)
      : 16;
    const lineHeightValue = style.line_height;
    const lineHeight = typeof lineHeightValue === "number" && Number.isFinite(lineHeightValue)
      ? Math.max(1, lineHeightValue)
      : fontSize * 1.2;
    const lines = content.split("\n");
    const weightFactor = font?.weight && font.weight >= 600 ? 1.03 : 1;
    const maxUnits = Math.max(0, ...lines.map((line) => Array.from(line).length));
    return {
      width: maxUnits * fontSize * 0.6 * weightFactor,
      height: Math.max(1, lines.length) * lineHeight,
      baseline: fontSize * 0.8,
    };
  }
}
