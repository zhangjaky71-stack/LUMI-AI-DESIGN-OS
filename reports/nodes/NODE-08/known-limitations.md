# NODE-08 — Known Limitations

1. This is a technology spike, not the production Canvas Engine or Design IR implementation.
2. Browser CI currently runs Chromium on Ubuntu. Edge and Safari-specific host validation remains part of the later production browser matrix.
3. Selection bounds are axis-aligned; production rotated multi-selection geometry is deferred to the formal Canvas Engine nodes.
4. Text editing uses a DOM textarea proof of concept. Rich typography, font licensing/loading, shaping, and pixel-identical export fidelity are later concerns.
5. Image previews are generated locally from asset references for the spike. Object-storage integration, thumbnail tiers, and signed URL policies belong to the Asset/Canvas implementation nodes.
6. The stress benchmark measures the CI/browser host that runs it. Results are evidence for feasibility, not a promise of identical frame times on every end-user machine.
7. The spike pins PixiJS 8.18.1 through an isolated CDN module import. Production dependency/version freezing is intentionally deferred until the formal Canvas Engine node after the renderer decision is revalidated.
8. WebGL is the primary automated path in this spike. WebGPU may be evaluated later but is not required for the baseline decision.
