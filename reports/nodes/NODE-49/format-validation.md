# NODE-49 Format Validation

Status: **IMPLEMENTED / hosted execution pending**

## Validation matrix

| Format | Implementation | Executable validation | Current evidence |
|---|---|---|---|
| PNG | Chromium Canvas `toBlob(image/png)` | re-decode + dimensions + PNG signature | implemented; hosted pending |
| JPEG | Chromium Canvas `toBlob(image/jpeg)` | re-decode + dimensions + SOI/EOI signature | implemented; hosted pending |
| WebP | Chromium Canvas `toBlob(image/webp)` | re-decode + dimensions + RIFF/WEBP signature | implemented; hosted pending |
| SVG | safe serializer | no external href/script, inline raster refs only, vector geometry required | unit tests implemented; hosted pending |
| PDF | deterministic PDF 1.7 raster-page writer | independent parser: header/xref/EOF/page count/MediaBox | unit tests implemented; hosted pending |
| ZIP | deterministic store-mode ZIP | CRC + local/central + EOCD + zip-slip checks | unit tests implemented; hosted pending |
| LUMI Package | ZIP envelope | required entries + sanitized Design IR + no URL/secret + CRC | unit tests implemented; hosted pending |

## Real raster test

`node scripts/export-raster-worker.test.mjs` launches pinned Chromium from `@playwright/test@1.61.1`, renders one SVG to PNG/JPEG/WebP, decodes each result again and checks exact 192×128 dimensions plus binary signatures.

This is real encoding evidence once executed; this report does not mark it PASS before a runner actually performs it.

## Explicitly unsupported / not verified

```text
PSD                unsupported
CMYK               no V1 color-management proof
Display P3         not verified in V1
bleed/crop marks   not implemented V1
```

No UI/API should advertise those capabilities as ready.

## Completion evidence required

1. Hosted `export-formats` job executes green with Chromium installed.
2. Artifact SDK SVG/PDF/ZIP tests execute green under Node 24 / TypeScript 6.
3. PostgreSQL export migration executes green.
4. No checksum/readback/package security regression.
