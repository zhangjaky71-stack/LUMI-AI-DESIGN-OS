import type {
  ConstraintViolation,
  DesignConstraint,
  PostflightContext,
  PostflightEvaluator,
} from "./types";

function parseHex(value: string): readonly [number, number, number] | null {
  const normalized = value.trim().replace(/^#/, "");
  const expanded =
    normalized.length === 3
      ? normalized
          .split("")
          .map((part) => `${part}${part}`)
          .join("")
      : normalized;
  if (!/^[0-9a-fA-F]{6}$/.test(expanded)) return null;
  return [
    Number.parseInt(expanded.slice(0, 2), 16),
    Number.parseInt(expanded.slice(2, 4), 16),
    Number.parseInt(expanded.slice(4, 6), 16),
  ];
}

function channel(value: number): number {
  const srgb = value / 255;
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(color: string): number | null {
  const parsed = parseHex(color);
  if (!parsed) return null;
  return 0.2126 * channel(parsed[0]) + 0.7152 * channel(parsed[1]) + 0.0722 * channel(parsed[2]);
}

export function contrastRatio(foreground: string, background: string): number | null {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  if (foregroundLuminance === null || backgroundLuminance === null) return null;
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Evaluates explicit structured colors only. Complex photographic backgrounds must use a separate
 * sampling/vision plugin; this evaluator does not pretend a single WCAG threshold fits every design.
 */
export class StructuredContrastEvaluator implements PostflightEvaluator {
  readonly name = "structured-contrast";
  readonly supported_types = ["REQUIRE_CONTRAST", "REQUIRE_TEXT_READABILITY"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  async evaluate(
    _context: PostflightContext,
    constraint: DesignConstraint,
  ): Promise<readonly ConstraintViolation[]> {
    const foreground = constraint.parameters.foreground;
    const background = constraint.parameters.background;
    const minimum =
      typeof constraint.parameters.min_ratio === "number" ? constraint.parameters.min_ratio : 4.5;
    if (typeof foreground !== "string" || typeof background !== "string") {
      throw new Error("Structured contrast requires foreground/background colors or a sampling plugin");
    }
    const ratio = contrastRatio(foreground, background);
    if (ratio === null) throw new Error("Unsupported color format");
    if (ratio >= minimum) return [];
    return [
      {
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: this.name,
        reason_code: "CONTRAST_BELOW_PROFILE_THRESHOLD",
        score: ratio,
        threshold: minimum,
        expected: minimum,
        actual: ratio,
        repair_hint: { action: "increase_contrast" },
      },
    ];
  }
}
