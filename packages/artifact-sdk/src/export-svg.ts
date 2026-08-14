import type { ExportSourceSnapshot, ExportVariant } from "./export-engine-types";

interface MatrixLike {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly e: number;
  readonly f: number;
}

interface BoundsLike {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

interface RenderItemLike {
  readonly id: string;
  readonly kind: string;
  readonly parent_id: string | null;
  readonly visible: boolean;
  readonly z_order: number;
  readonly world_matrix: MatrixLike;
  readonly local_bounds: BoundsLike;
  readonly world_bounds: BoundsLike;
  readonly resolved_style: Readonly<Record<string, unknown>>;
  readonly resolved_text?: {
    readonly content: string;
    readonly font?: { readonly family: string; readonly weight?: number; readonly style?: string };
  };
  readonly resolved_resource?: {
    readonly asset_id: string;
    readonly version: string;
    readonly status: string;
    readonly mime_type?: string;
  };
  readonly placeholder: boolean;
}

interface RenderPlanLike {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly items: readonly RenderItemLike[];
}

interface DesignNodeLike {
  readonly id: string;
  readonly kind: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

interface DesignDocumentLike {
  readonly document_id: string;
  readonly nodes: Readonly<Record<string, DesignNodeLike>>;
}

export interface ExportSvgResourceResolver {
  imageDataUri(args: {
    readonly asset_id: string;
    readonly version: string;
    readonly organization_id: string;
    readonly project_id: string;
  }): Promise<string>;
  embeddedFontCss?(args: {
    readonly family: string;
    readonly organization_id: string;
    readonly project_id: string;
  }): Promise<string | null>;
}

export interface SvgPage {
  readonly frame_id: string;
  readonly width: number;
  readonly height: number;
  readonly svg: string;
}

function finiteNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`EXPORT_SVG_${label}_INVALID`);
  return value;
}

function asMatrix(value: unknown): MatrixLike {
  if (!value || typeof value !== "object") throw new Error("EXPORT_SVG_MATRIX_INVALID");
  const row = value as Record<string, unknown>;
  return {
    a: finiteNumber(row.a, "MATRIX_A"),
    b: finiteNumber(row.b, "MATRIX_B"),
    c: finiteNumber(row.c, "MATRIX_C"),
    d: finiteNumber(row.d, "MATRIX_D"),
    e: finiteNumber(row.e, "MATRIX_E"),
    f: finiteNumber(row.f, "MATRIX_F"),
  };
}

function asBounds(value: unknown): BoundsLike {
  if (!value || typeof value !== "object") throw new Error("EXPORT_SVG_BOUNDS_INVALID");
  const row = value as Record<string, unknown>;
  return {
    x: finiteNumber(row.x, "BOUNDS_X"),
    y: finiteNumber(row.y, "BOUNDS_Y"),
    width: finiteNumber(row.width, "BOUNDS_WIDTH"),
    height: finiteNumber(row.height, "BOUNDS_HEIGHT"),
  };
}

function parseRenderPlan(value: unknown): RenderPlanLike {
  if (!value || typeof value !== "object") throw new Error("EXPORT_RENDER_PLAN_INVALID");
  const row = value as Record<string, unknown>;
  if (typeof row.compiler_version !== "string" || typeof row.document_id !== "string" || !Array.isArray(row.items)) {
    throw new Error("EXPORT_RENDER_PLAN_INVALID");
  }
  const items: RenderItemLike[] = row.items.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("EXPORT_RENDER_ITEM_INVALID");
    const item = raw as Record<string, unknown>;
    if (
      typeof item.id !== "string"
      || typeof item.kind !== "string"
      || !(typeof item.parent_id === "string" || item.parent_id === null)
      || typeof item.visible !== "boolean"
      || typeof item.z_order !== "number"
      || typeof item.placeholder !== "boolean"
      || !item.resolved_style
      || typeof item.resolved_style !== "object"
    ) {
      throw new Error("EXPORT_RENDER_ITEM_INVALID");
    }
    const resolvedText = item.resolved_text && typeof item.resolved_text === "object"
      ? item.resolved_text as RenderItemLike["resolved_text"]
      : undefined;
    const resolvedResource = item.resolved_resource && typeof item.resolved_resource === "object"
      ? item.resolved_resource as RenderItemLike["resolved_resource"]
      : undefined;
    return {
      id: item.id,
      kind: item.kind,
      parent_id: item.parent_id,
      visible: item.visible,
      z_order: item.z_order,
      world_matrix: asMatrix(item.world_matrix),
      local_bounds: asBounds(item.local_bounds),
      world_bounds: asBounds(item.world_bounds),
      resolved_style: item.resolved_style as Readonly<Record<string, unknown>>,
      ...(resolvedText ? { resolved_text: resolvedText } : {}),
      ...(resolvedResource ? { resolved_resource: resolvedResource } : {}),
      placeholder: item.placeholder,
    };
  });
  return { compiler_version: row.compiler_version, document_id: row.document_id, items };
}

function parseDesignDocument(value: unknown): DesignDocumentLike {
  if (!value || typeof value !== "object") throw new Error("EXPORT_DESIGN_DOCUMENT_INVALID");
  const row = value as Record<string, unknown>;
  if (typeof row.document_id !== "string" || !row.nodes || typeof row.nodes !== "object") {
    throw new Error("EXPORT_DESIGN_DOCUMENT_INVALID");
  }
  return { document_id: row.document_id, nodes: row.nodes as Readonly<Record<string, DesignNodeLike>> };
}

function escapeXml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

function safePaint(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  if (/^#[0-9a-fA-F]{3,8}$/.test(trimmed)) return trimmed;
  if (/^(?:rgb|rgba|hsl|hsla)\([0-9.,%\s+-]+\)$/.test(trimmed)) return trimmed;
  if (/^[a-zA-Z]+$/.test(trimmed)) return trimmed;
  return fallback;
}

function styleNumber(style: Readonly<Record<string, unknown>>, key: string, fallback: number): number {
  const value = style[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function matrixAttr(matrix: MatrixLike): string {
  return `matrix(${matrix.a} ${matrix.b} ${matrix.c} ${matrix.d} ${matrix.e} ${matrix.f})`;
}

function isDescendant(item: RenderItemLike, frameId: string, byId: ReadonlyMap<string, RenderItemLike>): boolean {
  if (item.id === frameId) return true;
  let current = item.parent_id;
  const seen = new Set<string>();
  while (current) {
    if (current === frameId) return true;
    if (seen.has(current)) throw new Error("EXPORT_RENDER_PLAN_PARENT_CYCLE");
    seen.add(current);
    current = byId.get(current)?.parent_id ?? null;
  }
  return false;
}

function dataImageUri(value: string): string {
  if (!/^data:image\/(?:png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(value)) {
    throw new Error("EXPORT_SVG_EXTERNAL_HREF_FORBIDDEN");
  }
  return value;
}

function vectorPath(document: DesignDocumentLike, id: string): string {
  const node = document.nodes[id];
  const raw = node?.metadata?.svg_path;
  if (typeof raw !== "string" || !raw.trim()) throw new Error("EXPORT_VECTOR_PATH_GEOMETRY_REQUIRED");
  if (/[<>]/.test(raw)) throw new Error("EXPORT_VECTOR_PATH_UNSAFE");
  return raw;
}

function itemStyle(item: RenderItemLike): string {
  const fill = safePaint(item.resolved_style.fill, "none");
  const stroke = safePaint(item.resolved_style.stroke, "none");
  const strokeWidth = Math.max(0, styleNumber(item.resolved_style, "stroke_width", 0));
  const opacity = Math.min(1, Math.max(0, styleNumber(item.resolved_style, "opacity", 1)));
  return `fill="${escapeXml(fill)}" stroke="${escapeXml(stroke)}" stroke-width="${strokeWidth}" opacity="${opacity}"`;
}

export class SafeSvgRenderPlanSerializer {
  readonly #resources: ExportSvgResourceResolver;

  constructor(resources: ExportSvgResourceResolver) {
    this.#resources = resources;
  }

  async renderPages(source: ExportSourceSnapshot, variant: ExportVariant): Promise<readonly SvgPage[]> {
    const plan = parseRenderPlan(source.render_plan);
    const document = parseDesignDocument(source.design_document);
    if (plan.document_id !== document.document_id || plan.document_id !== source.compiler_provenance.document_id) {
      throw new Error("EXPORT_SOURCE_DOCUMENT_IDENTITY_MISMATCH");
    }
    if (source.compiler_provenance.compile_hash.length !== 64) throw new Error("EXPORT_COMPILER_HASH_REQUIRED");
    if (!variant.frame_ids.length) throw new Error("EXPORT_FRAME_IDS_REQUIRED");
    const byId = new Map(plan.items.map((item) => [item.id, item] as const));
    const pages: SvgPage[] = [];
    for (const frameId of variant.frame_ids) {
      const frame = byId.get(frameId);
      if (!frame || frame.kind !== "FRAME" || !frame.visible) throw new Error(`EXPORT_FRAME_NOT_FOUND:${frameId}`);
      if (frame.placeholder) throw new Error(`EXPORT_FRAME_PLACEHOLDER:${frameId}`);
      const sourceWidth = frame.world_bounds.width;
      const sourceHeight = frame.world_bounds.height;
      if (sourceWidth <= 0 || sourceHeight <= 0) throw new Error("EXPORT_FRAME_DIMENSIONS_INVALID");
      const scale = variant.scale ?? 1;
      const width = variant.width ?? Math.max(1, Math.round(sourceWidth * scale));
      const height = variant.height ?? Math.max(1, Math.round(sourceHeight * scale));
      if (width <= 0 || height <= 0) throw new Error("EXPORT_TARGET_DIMENSIONS_INVALID");
      const selected = plan.items
        .filter((item) => item.visible && isDescendant(item, frameId, byId))
        .sort((a, b) => a.z_order - b.z_order);
      const fonts = new Set<string>();
      for (const item of selected) {
        const family = item.resolved_text?.font?.family;
        if (family) fonts.add(family);
      }
      const fontCss: string[] = [];
      if (this.#resources.embeddedFontCss) {
        for (const family of [...fonts].sort()) {
          const css = await this.#resources.embeddedFontCss({ family, organization_id: source.organization_id, project_id: source.project_id });
          if (css) {
            if (/@import|url\((?!['"]?data:)/i.test(css)) throw new Error("EXPORT_SVG_EXTERNAL_FONT_FORBIDDEN");
            fontCss.push(css);
          }
        }
      }
      const body: string[] = [];
      for (const item of selected) {
        if (item.kind === "DOCUMENT_ROOT" || item.kind === "GROUP" || item.kind === "COMPONENT" || item.kind === "INSTANCE" || item.kind === "GUIDE") continue;
        if (item.placeholder) throw new Error(`EXPORT_RENDER_PLACEHOLDER:${item.id}`);
        const transform = matrixAttr(item.world_matrix);
        const bounds = item.local_bounds;
        if (item.kind === "FRAME" || item.kind === "SHAPE" || item.kind === "MASK") {
          body.push(`<rect data-node-id="${escapeXml(item.id)}" x="0" y="0" width="${bounds.width}" height="${bounds.height}" transform="${transform}" ${itemStyle(item)}/>`);
          continue;
        }
        if (item.kind === "VECTOR_PATH") {
          body.push(`<path data-node-id="${escapeXml(item.id)}" d="${escapeXml(vectorPath(document, item.id))}" transform="${transform}" ${itemStyle(item)}/>`);
          continue;
        }
        if (item.kind === "TEXT") {
          const text = item.resolved_text?.content;
          if (typeof text !== "string") throw new Error("EXPORT_TEXT_CONTENT_REQUIRED");
          const family = item.resolved_text?.font?.family ?? "sans-serif";
          const size = Math.max(1, styleNumber(item.resolved_style, "font_size", 16));
          const weight = item.resolved_text?.font?.weight ?? 400;
          const fill = safePaint(item.resolved_style.fill, "#000000");
          body.push(`<text data-node-id="${escapeXml(item.id)}" x="0" y="${size}" transform="${transform}" font-family="${escapeXml(family)}" font-size="${size}" font-weight="${weight}" fill="${escapeXml(fill)}">${escapeXml(text)}</text>`);
          continue;
        }
        if (item.kind === "IMAGE") {
          const resource = item.resolved_resource;
          if (!resource || resource.status !== "READY") throw new Error("EXPORT_IMAGE_RESOURCE_NOT_READY");
          const href = dataImageUri(await this.#resources.imageDataUri({
            asset_id: resource.asset_id,
            version: resource.version,
            organization_id: source.organization_id,
            project_id: source.project_id,
          }));
          body.push(`<image data-node-id="${escapeXml(item.id)}" x="0" y="0" width="${bounds.width}" height="${bounds.height}" transform="${transform}" href="${href}" preserveAspectRatio="xMidYMid meet"/>`);
          continue;
        }
        if (item.kind === "VIDEO") throw new Error("EXPORT_VIDEO_NODE_REQUIRES_NODE_48");
        throw new Error(`EXPORT_NODE_KIND_UNSUPPORTED:${item.kind}`);
      }
      const background = variant.transparent_background ? "" : `<rect x="${frame.world_bounds.x}" y="${frame.world_bounds.y}" width="${sourceWidth}" height="${sourceHeight}" fill="${escapeXml(safePaint(variant.background, "#ffffff"))}"/>`;
      const style = fontCss.length ? `<style>${fontCss.join("\n")}</style>` : "";
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${frame.world_bounds.x} ${frame.world_bounds.y} ${sourceWidth} ${sourceHeight}">${style}${background}${body.join("")}</svg>`;
      if (/\b(?:href|src)=["']https?:/i.test(svg) || /<script\b/i.test(svg)) throw new Error("EXPORT_SVG_SANITIZE_FAILED");
      pages.push({ frame_id: frameId, width, height, svg });
    }
    return pages;
  }
}
