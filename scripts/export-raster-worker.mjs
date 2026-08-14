import { chromium } from "@playwright/test";
import process from "node:process";

const MIME = {
  PNG: "image/png",
  JPEG: "image/jpeg",
  WEBP: "image/webp",
};

export async function encodeSvgWithChromium({ svg, format, width, height, quality = 92 }) {
  if (typeof svg !== "string" || !svg.startsWith("<svg")) throw new Error("EXPORT_WORKER_SVG_INVALID");
  if (!(format in MIME)) throw new Error("EXPORT_WORKER_FORMAT_INVALID");
  if (!Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
    throw new Error("EXPORT_WORKER_DIMENSIONS_INVALID");
  }
  if (!Number.isInteger(quality) || quality < 1 || quality > 100) throw new Error("EXPORT_WORKER_QUALITY_INVALID");
  if (/\b(?:href|src)=["']https?:/i.test(svg) || /<script\b/i.test(svg)) {
    throw new Error("EXPORT_WORKER_EXTERNAL_RESOURCE_FORBIDDEN");
  }
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ serviceWorkers: "block" });
    await context.route(/^https?:\/\//, (route) => route.abort("blockedbyclient"));
    const page = await context.newPage();
    await page.setContent("<!doctype html><meta charset=utf-8><body></body>");
    const result = await page.evaluate(async ({ svgText, mime, widthPx, heightPx, qualityValue }) => {
      const blob = new Blob([svgText], { type: "image/svg+xml" });
      const url = URL.createObjectURL(blob);
      try {
        const image = new Image();
        image.decoding = "sync";
        image.src = url;
        await image.decode();
        const canvas = document.createElement("canvas");
        canvas.width = widthPx;
        canvas.height = heightPx;
        const context2d = canvas.getContext("2d", { alpha: mime !== "image/jpeg", colorSpace: "srgb" });
        if (!context2d) throw new Error("EXPORT_WORKER_CANVAS_CONTEXT_UNAVAILABLE");
        if (mime === "image/jpeg") {
          context2d.fillStyle = "#ffffff";
          context2d.fillRect(0, 0, widthPx, heightPx);
        }
        context2d.drawImage(image, 0, 0, widthPx, heightPx);
        const output = await new Promise((resolve, reject) => {
          canvas.toBlob(
            (encoded) => encoded ? resolve(encoded) : reject(new Error("EXPORT_WORKER_ENCODE_FAILED")),
            mime,
            qualityValue / 100,
          );
        });
        if (output.type !== mime) throw new Error(`EXPORT_WORKER_MIME_UNSUPPORTED:${output.type}`);
        const verificationUrl = URL.createObjectURL(output);
        try {
          const verificationImage = new Image();
          verificationImage.decoding = "sync";
          verificationImage.src = verificationUrl;
          await verificationImage.decode();
          if (verificationImage.naturalWidth !== widthPx || verificationImage.naturalHeight !== heightPx) {
            throw new Error(`EXPORT_WORKER_DECODE_DIMENSIONS_MISMATCH:${verificationImage.naturalWidth}x${verificationImage.naturalHeight}`);
          }
        } finally {
          URL.revokeObjectURL(verificationUrl);
        }
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(reader.error ?? new Error("EXPORT_WORKER_READ_FAILED"));
          reader.onload = () => resolve(String(reader.result));
          reader.readAsDataURL(output);
        });
        return { dataUrl, mimeType: output.type, byteLength: output.size, decodedWidth: widthPx, decodedHeight: heightPx };
      } finally {
        URL.revokeObjectURL(url);
      }
    }, {
      svgText: svg,
      mime: MIME[format],
      widthPx: width,
      heightPx: height,
      qualityValue: quality,
    });
    const marker = ";base64,";
    const markerIndex = result.dataUrl.indexOf(marker);
    if (markerIndex < 0) throw new Error("EXPORT_WORKER_DATA_URL_INVALID");
    const bytes = Buffer.from(result.dataUrl.slice(markerIndex + marker.length), "base64");
    if (bytes.length !== result.byteLength) throw new Error("EXPORT_WORKER_BYTE_LENGTH_MISMATCH");
    return { bytes: new Uint8Array(bytes), mime_type: result.mimeType, width: result.decodedWidth, height: result.decodedHeight };
  } finally {
    await browser.close();
  }
}

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString("utf8").trim();
  if (!text) throw new Error("EXPORT_WORKER_INPUT_REQUIRED");
  const request = JSON.parse(text);
  const result = await encodeSvgWithChromium(request);
  process.stdout.write(JSON.stringify({
    mime_type: result.mime_type,
    width: result.width,
    height: result.height,
    bytes_base64: Buffer.from(result.bytes).toString("base64"),
  }));
}

if (process.argv[1] && new URL(import.meta.url).pathname === process.argv[1]) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
