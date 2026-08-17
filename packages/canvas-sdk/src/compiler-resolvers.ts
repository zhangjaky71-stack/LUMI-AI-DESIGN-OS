import type { DesignDocument, JsonValue } from "../../design-ir/src/index";
import type {
  AssetCompileResolver,
  FontCompileResolver,
  ResolvedCompilerStyle,
  StyleCompileResolver,
  TextCompileMeasurer,
} from "./compiler-types";

function isRecord(value: unknown): value is Readonly<Record<string, JsonValue>> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resourceVersion(value: unknown): string {
  if (!isRecord(value)) return "missing";
  const version = value.version;
  return typeof version === "string" && version.length > 0 ? version : "unversioned";
}

export class DocumentStyleResolver implements StyleCompileResolver {
  resolveStyle(document: DesignDocument, styleRefs: readonly string[]) {
    const style: Record<string, JsonValue> = {};
    const versions: Record<string, string> = {};
    const missingRefs: string[] = [];
    for (const ref of styleRefs) {
      const value = document.resources[ref];
      if (!isRecord(value)) {
        missingRefs.push(ref);
        continue;
      }
      versions[ref] = resourceVersion(value);
      const payload = isRecord(value.value) ? value.value : value;
      for (const key of Object.keys(payload).sort()) {
        if (key === "version" || key === "kind") continue;
        style[key] = payload[key]!;
      }
    }
    return { style, missingRefs, versions };
  }
}

export class MissingAssetResolver implements AssetCompileResolver {
  async resolveAsset(): Promise<null> { return null; }
}

export class MissingFontResolver implements FontCompileResolver {
  async resolveFont(): Promise<null> { return null; }
}

function styleNumber(style: ResolvedCompilerStyle, key: string, fallback: number): number {
  const value = style[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export class DeterministicTextMeasurer implements TextCompileMeasurer {
  async measure(input: Parameters<TextCompileMeasurer["measure"]>[0]) {
    const fontSize = styleNumber(input.style, "fontSize", 16);
    const lineHeight = styleNumber(input.style, "lineHeight", fontSize * 1.2);
    const lines = input.content.split(/\r?\n/);
    const segmenter = typeof Intl.Segmenter === "function"
      ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
      : null;
    const graphemeCount = (line: string): number => segmenter
      ? [...segmenter.segment(line)].length
      : Array.from(line).length;
    const max = Math.max(0, ...lines.map(graphemeCount));
    return {
      width: Math.round(max * fontSize * 0.6 * 1_000) / 1_000,
      height: Math.round(Math.max(1, lines.length) * lineHeight * 1_000) / 1_000,
      baseline: Math.round(fontSize * 0.8 * 1_000) / 1_000,
    };
  }
}
