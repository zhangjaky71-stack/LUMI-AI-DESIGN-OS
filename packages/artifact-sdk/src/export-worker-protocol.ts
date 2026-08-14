import type { ExportRasterCodecPort } from "./export-renderer";

export interface RasterWorkerRequest {
  readonly svg: string;
  readonly format: "PNG" | "JPEG" | "WEBP";
  readonly width: number;
  readonly height: number;
  readonly quality: number;
}

export interface RasterWorkerResponse {
  readonly bytes: Uint8Array;
  readonly mime_type: string;
  readonly width: number;
  readonly height: number;
}

export interface RasterWorkerTransport {
  invoke(request: RasterWorkerRequest): Promise<RasterWorkerResponse>;
}

function expectedMime(format: RasterWorkerRequest["format"]): string {
  return format === "PNG" ? "image/png" : format === "JPEG" ? "image/jpeg" : "image/webp";
}

export class WorkerBackedRasterCodec implements ExportRasterCodecPort {
  readonly #transport: RasterWorkerTransport;

  constructor(transport: RasterWorkerTransport) {
    this.#transport = transport;
  }

  async encodeSvg(request: RasterWorkerRequest): Promise<{ bytes: Uint8Array; mime_type: string }> {
    const response = await this.#transport.invoke(request);
    if (!response.bytes.length) throw new Error("EXPORT_RASTER_WORKER_EMPTY");
    if (response.mime_type !== expectedMime(request.format)) throw new Error("EXPORT_RASTER_WORKER_MIME_MISMATCH");
    if (response.width !== request.width || response.height !== request.height) {
      throw new Error("EXPORT_RASTER_WORKER_DIMENSIONS_MISMATCH");
    }
    return { bytes: response.bytes, mime_type: response.mime_type };
  }
}
