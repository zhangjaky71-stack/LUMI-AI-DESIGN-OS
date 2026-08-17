import { violation } from "./identity";
import type {
  ConstraintViolation,
  DesignDocumentLike,
  DesignNodeLike,
  RuntimeConstraint,
  ValidationAdapters,
  ValidationPolicy,
} from "./types";

type Rect = readonly [number, number, number, number];
export type ValidatorFn = (
  document: DesignDocumentLike,
  constraint: RuntimeConstraint,
  impact: ReadonlySet<string>,
  adapters: ValidationAdapters,
  policy: ValidationPolicy,
) => readonly ConstraintViolation[];

export interface ValidatorSpec {
  readonly name: string;
  readonly constraintTypes: readonly string[];
  readonly fn: ValidatorFn;
}

function rect(node: DesignNodeLike): Rect | undefined {
  const raw =
    node.bounds && typeof node.bounds === "object"
      ? (node.bounds as Record<string, unknown>)
      : node.transform && typeof node.transform === "object"
        ? (node.transform as Record<string, unknown>)
        : undefined;
  if (!raw) return undefined;
  const x = typeof raw.x === "number" ? raw.x : 0;
  const y = typeof raw.y === "number" ? raw.y : 0;
  if (typeof raw.width !== "number" || typeof raw.height !== "number") return undefined;
  return [x, y, raw.width, raw.height];
}

function inside(inner: Rect, outer: Rect): boolean {
  return (
    inner[0] >= outer[0] &&
    inner[1] >= outer[1] &&
    inner[0] + inner[2] <= outer[0] + outer[2] &&
    inner[1] + inner[3] <= outer[1] + outer[3]
  );
}

function overlaps(left: Rect, right: Rect): boolean {
  return (
    left[0] < right[0] + right[2] &&
    left[0] + left[2] > right[0] &&
    left[1] < right[1] + right[3] &&
    left[1] + left[3] > right[1]
  );
}

function region(constraint: RuntimeConstraint): Rect | undefined {
  const raw = constraint.scope?.region ?? constraint.parameters?.region;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return undefined;
  const value = raw as Record<string, unknown>;
  if (typeof value.width !== "number" || typeof value.height !== "number") return undefined;
  return [
    typeof value.x === "number" ? value.x : 0,
    typeof value.y === "number" ? value.y : 0,
    value.width,
    value.height,
  ];
}

function targets(
  document: DesignDocumentLike,
  constraint: RuntimeConstraint,
  impact: ReadonlySet<string>,
): readonly string[] {
  let values: string[];
  const scoped = constraint.scope?.node_ids ?? [];
  if (scoped.length) values = [...scoped];
  else {
    const tags = new Set(constraint.scope?.semantic_tags ?? []);
    values = Object.entries(document.nodes)
      .filter(([, node]) => {
        if (!tags.size) return true;
        const semanticTags = Array.isArray(node.semantic_tags)
          ? node.semantic_tags.filter((item): item is string => typeof item === "string")
          : [];
        return (typeof node.role === "string" && tags.has(node.role)) || semanticTags.some((tag) => tags.has(tag));
      })
      .map(([id]) => id);
  }
  return values.filter((id) => document.nodes[id] && (!impact.size || impact.has(id))).sort();
}

function parseHex(value: string): readonly [number, number, number] | undefined {
  let text = value.startsWith("#") ? value.slice(1) : value;
  if (text.length === 3) text = [...text].map((char) => char + char).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(text)) return undefined;
  return [Number.parseInt(text.slice(0, 2), 16), Number.parseInt(text.slice(2, 4), 16), Number.parseInt(text.slice(4, 6), 16)];
}

function contrast(foreground: string, background: string): number | undefined {
  const a = parseHex(foreground);
  const b = parseHex(background);
  if (!a || !b) return undefined;
  const lum = (rgb: readonly [number, number, number]): number => {
    const channels = rgb.map((item) => {
      const v = item / 255;
      return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * channels[0]! + 0.7152 * channels[1]! + 0.0722 * channels[2]!;
  };
  const values = [lum(a), lum(b)].sort((x, y) => y - x);
  return (values[0]! + 0.05) / (values[1]! + 0.05);
}

const bounds: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const outer = region(constraint);
  if (!outer) return [];
  return targets(document, constraint, impact).flatMap((id) => {
    const nodeRect = rect(document.nodes[id]!);
    return nodeRect && !inside(nodeRect, outer)
      ? [violation(constraint, "BoundsValidator", [id], "NODE_OUT_OF_BOUNDS", "Node must remain inside the allowed bounds.", policy, { measured: nodeRect, expected: outer })]
      : [];
  });
};

const safeArea: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const outer = region(constraint);
  if (!outer) return [];
  return targets(document, constraint, impact).flatMap((id) => {
    const nodeRect = rect(document.nodes[id]!);
    return nodeRect && !inside(nodeRect, outer)
      ? [violation(constraint, "SafeAreaValidator", [id], "SAFE_AREA_VIOLATION", "Node crosses the configured safe area.", policy, { measured: nodeRect, expected: outer })]
      : [];
  });
};

const locked: ValidatorFn = (document, constraint, impact, _adapters, policy) =>
  targets(document, constraint, impact).map((id) =>
    violation(
      constraint,
      "LockedRegionValidator",
      [id],
      "LOCKED_NODE_MUTATION",
      "The operation violates an active lock constraint.",
      policy,
      { measured: "mutation", expected: "unchanged" },
    ),
  );

const textOverflow: ValidatorFn = (document, constraint, impact, adapters, policy) =>
  targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    if (node.kind !== "TEXT") return [];
    if (!adapters.text_measure) {
      const content = typeof node.content === "string" ? node.content : "";
      const precise = [...content].some((char) => char.codePointAt(0)! > 127) || constraint.parameters?.require_measurement !== false;
      return precise
        ? [violation(constraint, "TextOverflowValidator", [id], "TEXT_MEASUREMENT_UNAVAILABLE", "Exact text measurement is unavailable; overflow cannot be proven safe.", policy, { unavailable: true })]
        : [];
    }
    let measured: Readonly<Record<string, number>>;
    try {
      measured = adapters.text_measure(node);
    } catch {
      return [
        violation(
          constraint,
          "TextOverflowValidator",
          [id],
          "TEXT_MEASUREMENT_FAILED",
          "Text measurement adapter failed; overflow cannot be proven safe.",
          policy,
          { unavailable: true },
        ),
      ];
    }
    const box = rect(node);
    if (!box) return [];
    const values: ConstraintViolation[] = [];
    const width = measured.width ?? 0;
    const height = measured.height ?? 0;
    if (width > box[2] || height > box[3]) {
      values.push(violation(constraint, "TextOverflowValidator", [id], "TEXT_OVERFLOW", "Measured text exceeds the text box.", policy, { measured: { width, height }, expected: { width: box[2], height: box[3] } }));
    }
    const maxLines = constraint.parameters?.max_lines;
    if (typeof maxLines === "number" && (measured.lines ?? 0) > maxLines) {
      values.push(violation(constraint, "TextOverflowValidator", [id], "TEXT_MAX_LINES", "Text exceeds the configured maximum line count.", policy, { measured: measured.lines, expected: maxLines }));
    }
    return values;
  });

const fontSize: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const minimum = typeof constraint.parameters?.min_font_size === "number" ? constraint.parameters.min_font_size : 12;
  const forbidden = new Set(Array.isArray(constraint.parameters?.forbidden_fonts) ? constraint.parameters.forbidden_fonts.filter((item): item is string => typeof item === "string") : []);
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    if (node.kind !== "TEXT") return [];
    const values: ConstraintViolation[] = [];
    if (typeof node.font_size === "number" && node.font_size < minimum) {
      values.push(violation(constraint, "FontSizeValidator", [id], "FONT_SIZE_TOO_SMALL", "Text is smaller than the configured minimum font size.", policy, { measured: node.font_size, expected: minimum }));
    }
    if (typeof node.font_family === "string" && forbidden.has(node.font_family)) {
      values.push(violation(constraint, "FontSizeValidator", [id], "FORBIDDEN_FONT", "The selected font is forbidden by the active rule.", policy, { measured: node.font_family, expected: "allowed font" }));
    }
    if (typeof node.font_size === "number" && node.font_size > 0 && typeof node.line_height === "number") {
      const lineRatio = node.line_height / node.font_size;
      const minRatio = typeof constraint.parameters?.min_line_height_ratio === "number" ? constraint.parameters.min_line_height_ratio : 0.8;
      const maxRatio = typeof constraint.parameters?.max_line_height_ratio === "number" ? constraint.parameters.max_line_height_ratio : 2.0;
      if (lineRatio < minRatio || lineRatio > maxRatio) {
        values.push(violation(constraint, "FontSizeValidator", [id], "LINE_HEIGHT_UNREASONABLE", "Text line height is outside the configured readability range.", policy, { measured: lineRatio, expected: { min: minRatio, max: maxRatio } }));
      }
    }
    return values;
  });
};

const aspect: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const expected = constraint.parameters?.ratio;
  if (typeof expected !== "number") return [];
  const tolerance = typeof constraint.parameters?.tolerance === "number" ? constraint.parameters.tolerance : 0.01;
  return targets(document, constraint, impact).flatMap((id) => {
    const box = rect(document.nodes[id]!);
    if (!box || box[3] === 0) return [];
    const current = box[2] / box[3];
    return Math.abs(current - expected) > tolerance
      ? [violation(constraint, "AspectRatioValidator", [id], "ASPECT_RATIO_MISMATCH", "Node aspect ratio exceeds the permitted tolerance.", policy, { measured: current, expected })]
      : [];
  });
};

const contrastValidator: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const minimum = typeof constraint.parameters?.min_ratio === "number" ? constraint.parameters.min_ratio : 4.5;
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    const fg = typeof node.fill === "string" ? node.fill : typeof node.foreground === "string" ? node.foreground : undefined;
    const bg = typeof node.background === "string" ? node.background : typeof constraint.parameters?.background === "string" ? constraint.parameters.background : undefined;
    if (!fg || !bg) return [];
    const current = contrast(fg, bg);
    return current !== undefined && current < minimum
      ? [violation(constraint, "ContrastValidator", [id], "CONTRAST_TOO_LOW", "Foreground/background contrast is below the required ratio.", policy, { measured: current, expected: minimum })]
      : [];
  });
};

const protectedRegion: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const protectedRect = region(constraint);
  if (!protectedRect) return [];
  const allowed = new Set(Array.isArray(constraint.parameters?.allowed_node_ids) ? constraint.parameters.allowed_node_ids.filter((item): item is string => typeof item === "string") : []);
  return targets(document, constraint, impact).flatMap((id) => {
    if (allowed.has(id)) return [];
    const box = rect(document.nodes[id]!);
    return box && overlaps(box, protectedRect)
      ? [violation(constraint, "ProtectedRegionValidator", [id], "PROTECTED_REGION_OVERLAP", "Node overlaps a protected region.", policy, { measured: box, expected: { no_overlap: protectedRect } })]
      : [];
  });
};

const qr: ValidatorFn = (document, constraint, impact, adapters, policy) => {
  const minimum = typeof constraint.parameters?.min_size_px === "number" ? constraint.parameters.min_size_px : 96;
  const quiet = typeof constraint.parameters?.quiet_zone_px === "number" ? constraint.parameters.quiet_zone_px : 8;
  const scale = typeof constraint.parameters?.output_scale === "number" ? constraint.parameters.output_scale : 1;
  const requireDecode = constraint.parameters?.require_decode !== false;
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    if (node.role !== "QR_CODE" && !(constraint.scope?.node_ids?.length)) return [];
    const box = rect(node);
    if (!box) return [];
    const values: ConstraintViolation[] = [];
    const effective = Math.min(box[2], box[3]) * scale;
    if (effective < minimum) values.push(violation(constraint, "QRValidator", [id], "QR_TOO_SMALL", "QR effective raster size is below the configured minimum.", policy, { measured: effective, expected: minimum }));
    const actualQuiet = typeof node.quiet_zone_px === "number" ? node.quiet_zone_px : quiet;
    if (actualQuiet < quiet) values.push(violation(constraint, "QRValidator", [id], "QR_QUIET_ZONE_TOO_SMALL", "QR quiet zone is smaller than required.", policy, { measured: actualQuiet, expected: quiet }));
    const fg = typeof node.foreground === "string" ? node.foreground : "#000000";
    const bg = typeof node.background === "string" ? node.background : "#ffffff";
    const currentContrast = contrast(fg, bg);
    const minContrast = typeof constraint.parameters?.min_contrast_ratio === "number" ? constraint.parameters.min_contrast_ratio : 4.5;
    if (currentContrast !== undefined && currentContrast < minContrast) values.push(violation(constraint, "QRValidator", [id], "QR_CONTRAST_TOO_LOW", "QR contrast is below the scannability threshold.", policy, { measured: currentContrast, expected: minContrast }));
    if (requireDecode) {
      if (!adapters.qr_decode) {
        values.push(violation(constraint, "QRValidator", [id], "QR_DECODE_UNAVAILABLE", "Raster QR decoder is unavailable; scannability cannot be proven.", policy, { unavailable: true }));
      } else {
        try {
          if (!adapters.qr_decode(node)) {
            values.push(violation(constraint, "QRValidator", [id], "QR_DECODE_FAILED", "Rendered QR could not be decoded.", policy, { measured: false, expected: true }));
          }
        } catch {
          values.push(violation(constraint, "QRValidator", [id], "QR_DECODE_ADAPTER_FAILED", "QR decoder failed; scannability cannot be proven.", policy, { unavailable: true }));
        }
      }
    }
    return values;
  });
};

const brand: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const colors = new Set(Array.isArray(constraint.parameters?.allowed_colors) ? constraint.parameters.allowed_colors.filter((item): item is string => typeof item === "string") : []);
  const fonts = new Set(Array.isArray(constraint.parameters?.allowed_fonts) ? constraint.parameters.allowed_fonts.filter((item): item is string => typeof item === "string") : []);
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    const values: ConstraintViolation[] = [];
    if (colors.size && typeof node.fill === "string" && !colors.has(node.fill)) values.push(violation(constraint, "BrandTokenValidator", [id], "BRAND_COLOR_FORBIDDEN", "Node uses a color outside the approved brand token set.", policy, { measured: node.fill, expected: [...colors].sort() }));
    if (fonts.size && typeof node.font_family === "string" && !fonts.has(node.font_family)) values.push(violation(constraint, "BrandTokenValidator", [id], "BRAND_FONT_FORBIDDEN", "Node uses a font outside the approved brand token set.", policy, { measured: node.font_family, expected: [...fonts].sort() }));
    const transform = node.transform as Record<string, unknown> | undefined;
    if (node.role === "LOGO" && constraint.parameters?.logo_rotation_forbidden !== false && (transform?.rotation_deg ?? 0) !== 0) values.push(violation(constraint, "BrandTokenValidator", [id], "LOGO_TRANSFORM_FORBIDDEN", "Logo rotation is forbidden by the brand rule.", policy, { measured: transform?.rotation_deg, expected: 0 }));
    return values;
  });
};

const identity: ValidatorFn = (document, constraint, impact, adapters, policy) => {
  const threshold = typeof constraint.parameters?.min_score === "number" ? constraint.parameters.min_score : 0.9;
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    if (!adapters.identity_score) return [violation(constraint, "IdentityPreservationValidator", [id], "IDENTITY_BASELINE_UNAVAILABLE", "Identity feature baseline is unavailable; preservation cannot be proven.", policy, { unavailable: true })];
    let score: number | null;
    try {
      score = adapters.identity_score(node);
    } catch {
      return [violation(constraint, "IdentityPreservationValidator", [id], "IDENTITY_ADAPTER_FAILED", "Identity validator failed; preservation cannot be proven.", policy, { unavailable: true })];
    }
    if (score === null) return [violation(constraint, "IdentityPreservationValidator", [id], "IDENTITY_SCORE_UNAVAILABLE", "Identity score could not be produced.", policy, { unavailable: true })];
    return score < threshold ? [violation(constraint, "IdentityPreservationValidator", [id], "IDENTITY_SCORE_TOO_LOW", "Identity preservation score is below the configured threshold.", policy, { measured: score, expected: threshold })] : [];
  });
};

const exportDimension: ValidatorFn = (document, constraint, impact, _adapters, policy) => {
  const width = constraint.parameters?.width;
  const height = constraint.parameters?.height;
  if (typeof width !== "number" || typeof height !== "number") return [];
  return targets(document, constraint, impact).flatMap((id) => {
    const node = document.nodes[id]!;
    if (node.kind !== "FRAME") return [];
    const box = rect(node);
    return box && (box[2] !== width || box[3] !== height)
      ? [violation(constraint, "ExportDimensionValidator", [id], "EXPORT_DIMENSION_MISMATCH", "Frame dimensions do not match the export contract.", policy, { measured: { width: box[2], height: box[3] }, expected: { width, height } })]
      : [];
  });
};

export const VALIDATOR_SPECS: readonly ValidatorSpec[] = [
  { name: "BoundsValidator", constraintTypes: ["MUST_STAY_INSIDE"], fn: bounds },
  { name: "SafeAreaValidator", constraintTypes: ["SAFE_AREA"], fn: safeArea },
  { name: "LockedRegionValidator", constraintTypes: ["LOCK_POSITION", "LOCK_SIZE", "LOCK_ROTATION", "LOCK_TRANSFORM", "LOCK_LAYER_ORDER", "LOCK_PARENT", "LOCK_CONTENT", "LOCK_TEXT", "LOCK_ASSET", "LOCK_STYLE"], fn: locked },
  { name: "TextOverflowValidator", constraintTypes: ["REQUIRE_TEXT_READABILITY"], fn: textOverflow },
  { name: "FontSizeValidator", constraintTypes: ["REQUIRE_TEXT_READABILITY"], fn: fontSize },
  { name: "AspectRatioValidator", constraintTypes: ["LOCK_ASPECT_RATIO"], fn: aspect },
  { name: "ContrastValidator", constraintTypes: ["REQUIRE_CONTRAST"], fn: contrastValidator },
  { name: "ProtectedRegionValidator", constraintTypes: ["PROTECT_REGION", "MUST_NOT_OVERLAP"], fn: protectedRegion },
  { name: "QRValidator", constraintTypes: ["REQUIRE_SCANNABILITY"], fn: qr },
  { name: "BrandTokenValidator", constraintTypes: ["REQUIRE_BRAND_COMPLIANCE", "LOCK_BRAND"], fn: brand },
  { name: "IdentityPreservationValidator", constraintTypes: ["REQUIRE_IDENTITY_SCORE", "LOCK_IDENTITY"], fn: identity },
  { name: "ExportDimensionValidator", constraintTypes: ["REQUIRE_RESOLUTION"], fn: exportDimension },
];
