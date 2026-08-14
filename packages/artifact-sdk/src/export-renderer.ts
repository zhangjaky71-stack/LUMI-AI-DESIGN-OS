import type {
  ExportRendererPort,
  ExportSourceSnapshot,
  ExportVariant,
  RenderedExportPayload,
} from "./export-engine-types";
import { inspectRasterPdf, writeRasterPdf } from "./export-pdf";
import { assertExportProfile } from "./export-security";
import { SafeSvgRenderPlanSerializer } from "./export-svg";

export interface ExportRasterCodecPort {
  encodeSvg(args: {
    readonly svg: string;
    readonly format: "PNG" | "JPEG" | "WEBP";
    readonly width: number;
    readonly height: number;
    readonly quality: number;
  }): Promise<{ readonly bytes: Uint8Array; readonly mime_type: string }>;
}

function rasterMime(format: "PNG" | "JPEG" | "WEBP"): string {
  return format === "PNG" ? "image/png" : format === "JPEG" ? "image/jpeg" : "image/webp";
}

function quality(value: number | undefined): number {
  const resolved = value ?? 92;
  if (!Number.isInteger(resolved) || resolved < 1 || resolved > 100) throw new Error("EXPORT_QUALITY_INVALID");
  return resolved;
}

export class CompositeExportRenderer implements ExportRendererPort {
  readonly #svg: SafeSvgRenderPlanSerializer;
  readonly #raster: ExportRasterCodecPort;

  constructor(args: { readonly svg: SafeSvgRenderPlanSerializer; readonly raster: ExportRasterCodecPort }) {
    this.#svg = args.svg;
    this.#raster = args.raster;
  }

  async render(source: ExportSourceSnapshot, variant: ExportVariant): Promise<RenderedExportPayload> {
    assertExportProfile(variant.color_profile);
    if ((variant.bleed ?? 0) !== 0 || variant.crop_marks === true) {
      throw new Error("EXPORT_PRINT_MARKS_NOT_IMPLEMENTED_V1");
    }
    if (variant.resize_mode === "CROP" && (variant.width === undefined || variant.height === undefined)) {
      throw new Error("EXPORT_CROP_TARGET_DIMENSIONS_REQUIRED");
    }
    if (variant.format === "LUMI_PACKAGE" || variant.format === "ZIP") {
      throw new Error("EXPORT_PACKAGE_FORMAT_OWNED_BY_EXPORT_ENGINE");
    }
    const pages = await this.#svg.renderPages(source, variant);
    if (variant.format === "SVG") {
      if (pages.length !== 1) throw new Error("EXPORT_SVG_SINGLE_FRAME_REQUIRED");
      const page = pages[0]!;
      return {
        bytes: new TextEncoder().encode(page.svg),
        mime_type: "image/svg+xml",
        width: page.width,
        height: page.height,
      };
    }
    if (variant.format === "PDF") {
      const dpi = variant.dpi ?? 72;
      if (!Number.isInteger(dpi) || dpi < 36 || dpi > 1200) throw new Error("EXPORT_DPI_INVALID");
      const rasterPages = [];
      for (const page of pages) {
        const encoded = await this.#raster.encodeSvg({
          svg: page.svg,
          format: "JPEG",
          width: page.width,
          height: page.height,
          quality: quality(variant.quality),
        });
        if (encoded.mime_type !== "image/jpeg") throw new Error("EXPORT_PDF_RASTER_MIME_INVALID");
        rasterPages.push({ jpeg: encoded.bytes, width_px: page.width, height_px: page.height, dpi });
      }
      const bytes = writeRasterPdf(rasterPages);
      const inspection = inspectRasterPdf(bytes);
      if (inspection.page_count !== pages.length) throw new Error("EXPORT_PDF_PAGE_COUNT_MISMATCH");
      return {
        bytes,
        mime_type: "application/pdf",
        page_count: inspection.page_count,
        metadata: { media_boxes: inspection.media_boxes },
      };
    }
    if (variant.format === "PNG" || variant.format === "JPEG" || variant.format === "WEBP") {
      if (pages.length !== 1) throw new Error("EXPORT_RASTER_SINGLE_FRAME_REQUIRED");
      const page = pages[0]!;
      const encoded = await this.#raster.encodeSvg({
        svg: page.svg,
        format: variant.format,
        width: page.width,
        height: page.height,
        quality: quality(variant.quality),
      });
      if (encoded.mime_type !== rasterMime(variant.format)) throw new Error("EXPORT_RASTER_MIME_MISMATCH");
      return {
        bytes: encoded.bytes,
        mime_type: encoded.mime_type,
        width: page.width,
        height: page.height,
      };
    }
    throw new Error("EXPORT_FORMAT_UNSUPPORTED");
  }
}
