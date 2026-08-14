export interface PdfRasterPage {
  readonly jpeg: Uint8Array;
  readonly width_px: number;
  readonly height_px: number;
  readonly dpi: number;
}

export interface PdfInspection {
  readonly page_count: number;
  readonly media_boxes: readonly { readonly width_pt: number; readonly height_pt: number }[];
  readonly has_eof: boolean;
  readonly has_xref: boolean;
}

const encoder = new TextEncoder();

function ascii(value: string): Uint8Array {
  return encoder.encode(value);
}

function concat(chunks: readonly Uint8Array[]): Uint8Array {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function pagePoints(pixels: number, dpi: number): number {
  if (!Number.isFinite(pixels) || pixels <= 0 || !Number.isFinite(dpi) || dpi <= 0) {
    throw new Error("EXPORT_PDF_PAGE_DIMENSIONS_INVALID");
  }
  return Math.round((pixels * 72 / dpi) * 1000) / 1000;
}

export function writeRasterPdf(pages: readonly PdfRasterPage[]): Uint8Array {
  if (!pages.length) throw new Error("EXPORT_PDF_PAGES_REQUIRED");
  const objectChunks = new Map<number, Uint8Array>();
  const pageObjectIds: number[] = [];
  for (let index = 0; index < pages.length; index += 1) {
    const page = pages[index]!;
    if (!page.jpeg.length || page.width_px <= 0 || page.height_px <= 0) throw new Error("EXPORT_PDF_PAGE_INVALID");
    const pageId = 3 + index * 3;
    const imageId = pageId + 1;
    const contentId = pageId + 2;
    pageObjectIds.push(pageId);
    const widthPt = pagePoints(page.width_px, page.dpi);
    const heightPt = pagePoints(page.height_px, page.dpi);
    const content = `q\n${widthPt} 0 0 ${heightPt} 0 0 cm\n/Im${index} Do\nQ\n`;
    objectChunks.set(
      pageId,
      ascii(`${pageId} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${widthPt} ${heightPt}] /Resources << /XObject << /Im${index} ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>\nendobj\n`),
    );
    objectChunks.set(
      imageId,
      concat([
        ascii(`${imageId} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${page.width_px} /Height ${page.height_px} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpeg.length} >>\nstream\n`),
        page.jpeg,
        ascii("\nendstream\nendobj\n"),
      ]),
    );
    const contentBytes = ascii(content);
    objectChunks.set(
      contentId,
      concat([
        ascii(`${contentId} 0 obj\n<< /Length ${contentBytes.length} >>\nstream\n`),
        contentBytes,
        ascii("endstream\nendobj\n"),
      ]),
    );
  }
  objectChunks.set(1, ascii("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"));
  objectChunks.set(2, ascii(`2 0 obj\n<< /Type /Pages /Count ${pages.length} /Kids [${pageObjectIds.map((id) => `${id} 0 R`).join(" ")}] >>\nendobj\n`));
  const maxObjectId = 2 + pages.length * 3;
  const header = concat([ascii("%PDF-1.7\n%"), new Uint8Array([0xe2, 0xe3, 0xcf, 0xd3]), ascii("\n")]);
  const chunks: Uint8Array[] = [header];
  const offsets = new Array<number>(maxObjectId + 1).fill(0);
  let cursor = header.length;
  for (let id = 1; id <= maxObjectId; id += 1) {
    const chunk = objectChunks.get(id);
    if (!chunk) throw new Error(`EXPORT_PDF_OBJECT_MISSING:${id}`);
    offsets[id] = cursor;
    chunks.push(chunk);
    cursor += chunk.length;
  }
  const xrefOffset = cursor;
  const xrefRows = ["xref", `0 ${maxObjectId + 1}`, "0000000000 65535 f "];
  for (let id = 1; id <= maxObjectId; id += 1) {
    xrefRows.push(`${String(offsets[id]).padStart(10, "0")} 00000 n `);
  }
  chunks.push(ascii(`${xrefRows.join("\n")}\ntrailer\n<< /Size ${maxObjectId + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`));
  return concat(chunks);
}

export function inspectRasterPdf(bytes: Uint8Array): PdfInspection {
  if (bytes.length < 32) throw new Error("EXPORT_PDF_TOO_SMALL");
  const text = new TextDecoder("latin1").decode(bytes);
  if (!text.startsWith("%PDF-1.")) throw new Error("EXPORT_PDF_HEADER_INVALID");
  const hasEof = /%%EOF\s*$/.test(text);
  const hasXref = /\nxref\n/.test(text) && /\nstartxref\n\d+\n%%EOF/.test(text);
  if (!hasEof || !hasXref) throw new Error("EXPORT_PDF_STRUCTURE_INVALID");
  const pageMatches = [...text.matchAll(/\/Type\s*\/Page\b[\s\S]*?\/MediaBox\s*\[0\s+0\s+([0-9.]+)\s+([0-9.]+)\]/g)];
  if (!pageMatches.length) throw new Error("EXPORT_PDF_NO_PAGES");
  const mediaBoxes = pageMatches.map((match) => ({
    width_pt: Number(match[1]),
    height_pt: Number(match[2]),
  }));
  if (mediaBoxes.some((box) => !Number.isFinite(box.width_pt) || !Number.isFinite(box.height_pt) || box.width_pt <= 0 || box.height_pt <= 0)) {
    throw new Error("EXPORT_PDF_MEDIABOX_INVALID");
  }
  return { page_count: pageMatches.length, media_boxes: mediaBoxes, has_eof: hasEof, has_xref: hasXref };
}
