import { describe, expect, it } from "vitest";

import type { DesignDocument } from "../../design-ir/src/index";
import { CanvasCompiler } from "./compiler";
import { CanvasCompilerCache, canvasCompilerCacheKey } from "./compiler-cache";
import { planCompilerDirtyNodes } from "./compiler-dirty";
import type {
  CompilerAssetResolver,
  CompilerFontResolver,
  ResolvedCompilerFont,
  ResolvedCompilerResource,
} from "./compiler-types";
import { CanvasController } from "./controller";

function fixture(uri = "https://signed.example/asset?token=one"): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "compiler-doc",
    unit: "px",
    root_id: "root",
    nodes: {
      root: {
        id: "root",
        kind: "DOCUMENT_ROOT",
        parent_id: null,
        children: ["frame"],
      },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["title", "image"],
        transform: { x: 100, y: 50, width: 600, height: 400 },
        style_refs: ["style-frame"],
      },
      title: {
        id: "title",
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content: "LUMI 编译器",
        transform: { x: 32, y: 24, width: 240, height: 48 },
        style_refs: ["style-title"],
        metadata: { font_asset_id: "font-inter" },
      },
      image: {
        id: "image",
        kind: "IMAGE",
        parent_id: "frame",
        children: [],
        asset_id: "asset-product",
        transform: { x: 80, y: 120, width: 320, height: 220 },
      },
    },
    resources: {
      "style-frame": { style: { fill: "#ffffff" }, version: "style-1" },
      "style-title": {
        style: { font_size: 32, line_height: 40, fill: "#111111" },
        version: "style-2",
      },
      "font-inter": {
        family: "Inter",
        version: "font-v4",
        uri: "https://signed.example/font?token=one",
        weight: 500,
      },
      "asset-product": {
        version: "asset-v7",
        preview_uri: uri,
        mime_type: "image/png",
        width: 1600,
        height: 1200,
      },
    },
    metadata: { document_version: 9 },
  };
}

function movedTitle(document: DesignDocument): DesignDocument {
  const title = document.nodes.title!;
  return {
    ...document,
    nodes: {
      ...document.nodes,
      title: {
        ...title,
        transform: { ...title.transform, x: 52 },
      },
    },
    metadata: { ...document.metadata, document_version: 10 },
  };
}

describe("NODE-41 full compiler", () => {
  it("produces deterministic render plan and compiler provenance without persisting signed URLs", async () => {
    const document = fixture();
    const before = JSON.stringify(document);
    const compiler = new CanvasCompiler();
    const first = await compiler.fullCompile(document);
    const second = await compiler.fullCompile(document);
    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
    if (!first.ok || !second.ok) return;

    expect(first.snapshot.compiler_version).toBe("1.0.0");
    expect(first.snapshot.provenance.compiler_version).toBe("1.0.0");
    expect(first.snapshot.provenance.document_version).toBe(9);
    expect(first.snapshot.provenance.resource_versions).toEqual({
      "asset-product": "asset-v7",
    });
    expect(first.snapshot.provenance.font_versions).toEqual({
      "font-inter": "font-v4",
    });
    expect(first.snapshot.provenance.compile_hash).toBe(second.snapshot.provenance.compile_hash);
    expect(first.snapshot.render_plan.items.map((item) => item.id)).toEqual([
      "root",
      "frame",
      "title",
      "image",
    ]);
    expect(first.snapshot.nodes.get("title")?.resolved_text?.metrics?.width).toBeGreaterThan(0);
    expect(JSON.stringify(document)).toBe(before);
  });

  it("keeps compile hash stable when only an expiring URI changes but resource version is unchanged", async () => {
    const compiler = new CanvasCompiler();
    const first = await compiler.fullCompile(fixture("https://signed.example/a?token=1"));
    const second = await compiler.fullCompile(fixture("https://signed.example/a?token=2"));
    expect(first.ok && second.ok).toBe(true);
    if (!first.ok || !second.ok) return;
    expect(first.snapshot.provenance.compile_hash).toBe(second.snapshot.provenance.compile_hash);
  });

  it("emits missing resource diagnostics while preserving a renderable placeholder", async () => {
    const document = fixture();
    const next: DesignDocument = {
      ...document,
      resources: Object.fromEntries(
        Object.entries(document.resources).filter(([key]) => key !== "asset-product"),
      ),
    };
    const result = await new CanvasCompiler().fullCompile(next);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.snapshot.nodes.get("image")?.resolved_resource?.status).toBe("MISSING");
    expect(result.diagnostics.some((item) => item.code === "RESOURCE_MISSING")).toBe(true);
  });

  it("rejects globally invalid graph cycles", () => {
    const document = fixture();
    const root = document.nodes.root!;
    const frame = document.nodes.frame!;
    const cyclic: DesignDocument = {
      ...document,
      nodes: {
        ...document.nodes,
        root: { ...root, parent_id: "frame" },
        frame: { ...frame, children: [...frame.children, "root"] },
      },
    };
    const result = new CanvasCompiler().compileStructure(cyclic);
    expect(result.ok).toBe(false);
    expect(result.diagnostics.some((item) => item.source === "IR_GRAPH_CYCLE")).toBe(true);
  });

  it("turns custom renderer-unsupported nodes into explicit placeholders", () => {
    const document = fixture();
    const frame = document.nodes.frame!;
    const custom = {
      id: "plugin-node",
      kind: "custom:plugin",
      parent_id: "frame",
      children: [],
      transform: { x: 10, y: 10, width: 100, height: 100 },
    } as const;
    const next: DesignDocument = {
      ...document,
      nodes: {
        ...document.nodes,
        frame: { ...frame, children: [...frame.children, custom.id] },
        [custom.id]: custom,
      },
    };
    const result = new CanvasCompiler().compileStructure(next);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.snapshot.nodes.get(custom.id)?.placeholder).toBe(true);
    expect(result.diagnostics.some((item) => item.code === "NODE_PLACEHOLDER")).toBe(true);
  });
});

describe("NODE-41 incremental compiler", () => {
  it("matches a fresh full compile for a geometry change", async () => {
    const compiler = new CanvasCompiler();
    const before = fixture();
    const initial = await compiler.fullCompile(before);
    expect(initial.ok).toBe(true);
    if (!initial.ok) return;
    const after = movedTitle(before);
    const incremental = await compiler.incrementalCompile({
      previous: initial.snapshot,
      before,
      after,
    });
    const full = await compiler.fullCompile(after);
    expect(incremental.ok && full.ok).toBe(true);
    if (!incremental.ok || !full.ok || !("patch" in incremental)) return;
    expect(incremental.fallback_to_full).toBe(false);
    expect(incremental.dirty_node_ids).toContain("title");
    expect(incremental.patch.upserted_nodes.map((node) => node.id)).toContain("title");
    expect(incremental.snapshot.provenance.compile_hash).toBe(full.snapshot.provenance.compile_hash);
    expect(incremental.snapshot.render_plan).toEqual(full.snapshot.render_plan);
  });

  it("marks resource/style dependents dirty when resource definitions change", () => {
    const before = fixture();
    const after: DesignDocument = {
      ...before,
      resources: {
        ...before.resources,
        "style-title": {
          style: { font_size: 36, line_height: 44, fill: "#111111" },
          version: "style-3",
        },
      },
    };
    const plan = planCompilerDirtyNodes(before, after);
    expect(plan.resource_ids).toContain("style-title");
    expect(plan.dirty_node_ids).toContain("title");
  });

  it("falls back to full compile when compiler version changes", async () => {
    const before = fixture();
    const v1 = new CanvasCompiler({ compiler_version: "1.0.0" });
    const initial = await v1.fullCompile(before);
    expect(initial.ok).toBe(true);
    if (!initial.ok) return;
    const v2 = new CanvasCompiler({ compiler_version: "2.0.0" });
    const result = await v2.incrementalCompile({
      previous: initial.snapshot,
      before,
      after: movedTitle(before),
    });
    expect(result.ok).toBe(true);
    if (!result.ok || !("patch" in result)) return;
    expect(result.fallback_to_full).toBe(true);
    expect(result.snapshot.compiler_version).toBe("2.0.0");
  });
});

describe("NODE-41 resolver and cache boundaries", () => {
  it("accepts authorized async resource/font resolvers without changing compiler contracts", async () => {
    const assetResolver: CompilerAssetResolver = {
      async resolveAsset(_document, assetId, variant): Promise<ResolvedCompilerResource> {
        return {
          asset_id: assetId,
          variant,
          version: "authorized-v1",
          status: "READY",
          fingerprint: `${assetId}:${variant}:authorized-v1`,
          uri: "memory://authorized",
        };
      },
    };
    const fontResolver: CompilerFontResolver = {
      async resolveFont(_document, fontRef): Promise<ResolvedCompilerFont> {
        return {
          font_ref: fontRef,
          family: "Inter",
          version: "authorized-font-v1",
          status: "READY",
          fingerprint: `${fontRef}:authorized-font-v1`,
        };
      },
    };
    const result = await new CanvasCompiler({ asset_resolver: assetResolver, font_resolver: fontResolver }).fullCompile(fixture());
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.snapshot.provenance.resource_versions["asset-product"]).toBe("authorized-v1");
    expect(result.snapshot.provenance.font_versions["font-inter"]).toBe("authorized-font-v1");
  });

  it("provides stable document/compiler cache keys and bounded LRU storage", async () => {
    const document = fixture();
    const first = await canvasCompilerCacheKey("1.0.0", document);
    const second = await canvasCompilerCacheKey("1.0.0", document);
    expect(first).toBe(second);
    const compiled = await new CanvasCompiler().fullCompile(document);
    expect(compiled.ok).toBe(true);
    if (!compiled.ok) return;
    const cache = new CanvasCompilerCache(1);
    cache.set("one", compiled.snapshot);
    cache.set("two", compiled.snapshot);
    expect(cache.size).toBe(1);
    expect(cache.get("one")).toBeNull();
    expect(cache.get("two")).not.toBeNull();
  });

  it("routes production CanvasController scene construction through the compiler port", () => {
    let calls = 0;
    const compiler = new CanvasCompiler();
    const controller = new CanvasController(fixture(), {
      compiler: {
        compileStructure(document) {
          calls += 1;
          return compiler.compileStructure(document);
        },
      },
    });
    expect(calls).toBe(1);
    expect("compiler_version" in controller.snapshot().scene).toBe(true);
    controller.replaceDocument(movedTitle(fixture()));
    expect(calls).toBe(2);
  });
});
