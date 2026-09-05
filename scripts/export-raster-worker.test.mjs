import assert from "node:assert/strict";
import { encodeSvgWithChromium } from "./export-raster-worker.mjs";

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64"><rect width="96" height="64" fill="#f0c400"/><circle cx="48" cy="32" r="18" fill="#111111"/></svg>`;

function assertSignature(format, bytes) {
  if (format === "PNG") {
    assert.deepEqual([...bytes.slice(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    return;
  }
  if (format === "JPEG") {
    assert.equal(bytes[0], 0xff);
    assert.equal(bytes[1], 0xd8);
    assert.equal(bytes[bytes.length - 2], 0xff);
    assert.equal(bytes[bytes.length - 1], 0xd9);
    return;
  }
  const prefix = new TextDecoder("ascii").decode(bytes.slice(0, 4));
  const webp = new TextDecoder("ascii").decode(bytes.slice(8, 12));
  assert.equal(prefix, "RIFF");
  assert.equal(webp, "WEBP");
}

for (const format of ["PNG", "JPEG", "WEBP"]) {
  const result = await encodeSvgWithChromium({ svg, format, width: 192, height: 128, quality: 90 });
  assert.equal(result.mime_type, format === "PNG" ? "image/png" : format === "JPEG" ? "image/jpeg" : "image/webp");
  assert.equal(result.width, 192);
  assert.equal(result.height, 128);
  assert.ok(result.bytes.length > 100);
  assertSignature(format, result.bytes);
}

await assert.rejects(
  () => encodeSvgWithChromium({ svg: `<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.invalid/a.png"/></svg>`, format: "PNG", width: 32, height: 32 }),
  /EXPORT_WORKER_EXTERNAL_RESOURCE_FORBIDDEN/,
);

console.log("NODE-49 Chromium raster worker: PNG/JPEG/WebP OK");
