import { describe, expect, it } from "vitest";
import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import {
  CanvasCompiler,
  applyCompiledPatch,
  compiledSceneToCanvasScene,
  type AssetCompileResolver,
  type FontCompileResolver,
  type ResolvedCompilerAsset,
  type ResolvedCompilerFont,
} from "../src/index";
import fixture from "../fixtures/compiler-snapshot-v1.json";

function document(): DesignDocument {
  const nodes: Record<string, DesignNode> = {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
    frame: {
      id: "frame", kind: "FRAME", parent_id: "root", children: ["title", "hero", "mask", "badge"],
      transform: { x: 100, y: 50, width: 800, height: 600 },
    },
    title: {
      id: "title", kind: "TEXT", parent_id: "frame", children: [], content: "你好 LUMI 👋",
      font_ref: "font-main", style_refs: ["token-body"],
      transform: { x: 40, y: 30, width: 320, height: 48 },
    },
    hero: {
      id: "hero", kind: "IMAGE", parent_id: "frame", children: [], asset_id: "asset-hero",
      transform: { x: 40, y: 110, width: 480, height: 320 },
    },
    mask: {
      id: "mask", kind: "MASK", parent_id: "frame", children: [],
      transform: { x: 500, y: 30, width: 180, height: 180 },
    },
    badge: {
      id: "badge", kind: "SHAPE", parent_id: "frame", children: [], mask_id: "mask",
      transform: { x: 520, y: 50, width: 120, height: 120 },
    },
  };
  return {
    schema_version: "2.0", document_id: "fixture-poster", unit: "px", root_id: "root", nodes,
    resources: {
      "token-body": { kind: "style", version: "style-v1", value: { fontSize: 20, lineHeight: 24, fill: "#fff" } },
    },
    metadata: {},
  };
}

class AssetResolver implements AssetCompileResolver {
  calls = 0;
  urlSequence = 0;
  version = "asset-v7";
  async resolveAsset(input: Parameters<AssetCompileResolver["resolveAsset"]>[0]): Promise<ResolvedCompilerAsset | null> {
    this.calls += 1;
    this.urlSequence += 1;
    return {
      assetId: input.assetId, kind: "image", tier: input.tier, resourceVersion: this.version,
      fingerprint: `${input.assetId}:${this.version}`, status: "ready",
      authorizedUrl: `https://signed.example/${input.assetId}?nonce=${this.urlSequence}`,
      mimeType: "image/webp", width: 1200, height: 800,
    };
  }
}

class FontResolver implements FontCompileResolver {
  calls = 0;
  version = "font-v3";
  async resolveFont(input: Parameters<FontCompileResolver["resolveFont"]>[0]): Promise<ResolvedCompilerFont | null> {
    this.calls += 1;
    return {
      fontRef: input.fontRef, family: "LUMI Sans", style: "normal", weight: 400,
      resourceVersion: this.version, fingerprint: `${input.fontRef}:${this.version}`, status: "ready",
      authorizedUrl: `https://signed.example/fonts/${input.fontRef}?v=${this.version}`,
    };
  }
}

function cloneDocument(value: DesignDocument): DesignDocument { return structuredClone(value); }

describe("NODE-41 Canvas Compiler", () => {
  it("full-compiles the fixture with deterministic resource/version provenance", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver();
    const compiler = new CanvasCompiler({ assetResolver: assets, fontResolver: fonts });
    const first = await compiler.compileFull(document()); const second = await compiler.compileFull(document());
    expect(first.ok).toBe(true); expect(second.ok).toBe(true);
    if (!first.ok || !second.ok) return;
    expect(first.snapshot.compilerVersion).toBe(fixture.compilerVersion);
    expect(first.snapshot.orderedIds).toEqual(fixture.orderedIds);
    expect(first.snapshot.provenance.resource_versions).toEqual(fixture.resourceVersions);
    expect(first.snapshot.provenance.font_versions).toEqual(fixture.fontVersions);
    expect(first.snapshot.provenance.token_versions).toEqual(fixture.tokenVersions);
    expect(first.snapshot.sceneHash).toBe(second.snapshot.sceneHash);
    expect(first.snapshot.nodes.get("hero")?.resolvedResource?.authorizedUrl)
      .not.toBe(second.snapshot.nodes.get("hero")?.resolvedResource?.authorizedUrl);
  });

  it("rejects globally invalid structure instead of compiling a corrupt scene", async () => {
    const broken = cloneDocument(document());
    const nodes = structuredClone(broken.nodes) as Record<string, DesignNode>;
    nodes.root = { ...nodes.root!, children: ["missing"] };
    const result = await new CanvasCompiler().compileFull({ ...broken, nodes });
    expect(result.ok).toBe(false);
    expect(result.diagnostics.some((item) => item.code === "COMPILER_STRUCTURAL_INVALID")).toBe(true);
  });

  it("isolates a missing asset as a placeholder without failing other nodes", async () => {
    const result = await new CanvasCompiler({ fontResolver: new FontResolver() }).compileFull(document());
    expect(result.ok).toBe(true); if (!result.ok) return;
    expect(result.snapshot.nodes.get("hero")?.placeholder).toBe(true);
    expect(result.snapshot.nodes.get("title")?.placeholder).toBe(false);
    expect(result.diagnostics.some((item) => item.nodeId === "hero" && item.code === "COMPILER_RESOURCE_MISSING")).toBe(true);
  });

  it("incremental geometry compile is scene-hash equivalent to a full compile", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver();
    const compiler = new CanvasCompiler({ assetResolver: assets, fontResolver: fonts });
    const before = document(); const initial = await compiler.compileFull(before); expect(initial.ok).toBe(true); if (!initial.ok) return;
    const after = cloneDocument(before); const nodes = structuredClone(after.nodes) as Record<string, DesignNode>;
    nodes.frame = { ...nodes.frame!, transform: { ...nodes.frame!.transform, x: 180 } };
    const changed = { ...after, nodes };
    const incremental = await compiler.compileIncremental({ previous: initial.snapshot, before, after: changed });
    const full = await compiler.compileFull(changed);
    expect(incremental.ok).toBe(true); expect(full.ok).toBe(true); if (!incremental.ok || !full.ok) return;
    expect(incremental.snapshot.sceneHash).toBe(full.snapshot.sceneHash);
    expect(incremental.dirtyNodeIds).toContain("title");
    expect(incremental.snapshot.nodes.get("title")?.worldBounds.x).toBe(full.snapshot.nodes.get("title")?.worldBounds.x);
  });

  it("detects resource-table changes omitted by node-level semantic diff", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver();
    const compiler = new CanvasCompiler({ assetResolver: assets, fontResolver: fonts });
    const before = document(); const initial = await compiler.compileFull(before); expect(initial.ok).toBe(true); if (!initial.ok) return;
    const after = cloneDocument(before);
    const resources = structuredClone(after.resources) as Record<string, any>;
    resources["token-body"] = { ...resources["token-body"], version: "style-v2", value: { ...resources["token-body"].value, fontSize: 24 } };
    const changed = { ...after, resources };
    const incremental = await compiler.compileIncremental({ previous: initial.snapshot, before, after: changed });
    const full = await compiler.compileFull(changed);
    expect(incremental.ok).toBe(true); expect(full.ok).toBe(true); if (!incremental.ok || !full.ok) return;
    expect(incremental.dirtyNodeIds).toContain("title");
    expect(incremental.snapshot.sceneHash).toBe(full.snapshot.sceneHash);
    expect(incremental.snapshot.provenance.token_versions["token-body"]).toBe("style-v2");
  });

  it("recompiles only font dependents after an async font-version invalidation", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver();
    const compiler = new CanvasCompiler({ assetResolver: assets, fontResolver: fonts });
    const doc = document(); const initial = await compiler.compileFull(doc); expect(initial.ok).toBe(true); if (!initial.ok) return;
    const assetCalls = assets.calls; const fontCalls = fonts.calls; fonts.version = "font-v4";
    const update = await compiler.compileResourceInvalidation(initial.snapshot, doc, { fontRefs: ["font-main"] });
    expect(update.ok).toBe(true); if (!update.ok) return;
    expect(update.dirtyNodeIds).toEqual(["title"]);
    expect(fonts.calls).toBe(fontCalls + 1);
    expect(assets.calls).toBe(assetCalls);
    expect(update.snapshot.provenance.font_versions["font-main"]).toBe("font-v4");
  });

  it("recompiles asset dependents after an authorized resource version changes", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver();
    const compiler = new CanvasCompiler({ assetResolver: assets, fontResolver: fonts });
    const doc = document(); const initial = await compiler.compileFull(doc); expect(initial.ok).toBe(true); if (!initial.ok) return;
    assets.version = "asset-v8";
    const update = await compiler.compileResourceInvalidation(initial.snapshot, doc, { assetIds: ["asset-hero"] });
    expect(update.ok).toBe(true); if (!update.ok) return;
    expect(update.dirtyNodeIds).toEqual(["hero"]);
    expect(update.snapshot.provenance.resource_versions["asset-hero"]).toBe("asset-v8");
    expect(update.patch.upsertedNodes.map((item) => item.id)).toEqual(["hero"]);
  });

  it("reports missing mask references on a single node without global failure", async () => {
    const doc = cloneDocument(document()); const nodes = structuredClone(doc.nodes) as Record<string, DesignNode>;
    nodes.badge = { ...nodes.badge!, mask_id: "missing-mask" };
    const result = await new CanvasCompiler({ assetResolver: new AssetResolver(), fontResolver: new FontResolver() })
      .compileFull({ ...doc, nodes });
    expect(result.ok).toBe(true); if (!result.ok) return;
    expect(result.diagnostics.some((item) => item.nodeId === "badge" && item.code === "COMPILER_MASK_REFERENCE_MISSING")).toBe(true);
    expect(result.snapshot.nodes.get("badge")?.kind).toBe("SHAPE");
  });

  it("falls back to full compile across compiler-version boundaries", async () => {
    const assets = new AssetResolver(); const fonts = new FontResolver(); const doc = document();
    const oldCompiler = new CanvasCompiler({ compilerVersion: "0.9.0", assetResolver: assets, fontResolver: fonts });
    const old = await oldCompiler.compileFull(doc); expect(old.ok).toBe(true); if (!old.ok) return;
    const nextCompiler = new CanvasCompiler({ compilerVersion: "1.0.0", assetResolver: assets, fontResolver: fonts });
    const result = await nextCompiler.compileIncremental({ previous: old.snapshot, before: doc, after: doc });
    expect(result.ok).toBe(true); if (!result.ok) return;
    expect(result.fallbackToFull).toBe(true);
    expect(result.diagnostics.some((item) => item.code === "COMPILER_VERSION_MISMATCH")).toBe(true);
  });

  it("emits compiler provenance through the Artifact provenance sink", async () => {
    const compiler = new CanvasCompiler({ assetResolver: new AssetResolver(), fontResolver: new FontResolver() });
    const result = await compiler.compileFull(document()); expect(result.ok).toBe(true); if (!result.ok) return;
    let recorded: unknown = null;
    await compiler.recordProvenance(result.snapshot, { recordCompilerProvenance(value) { recorded = value; } });
    expect(recorded).toEqual(result.snapshot.provenance);
    expect(result.snapshot.provenance.compiler_version).toBe("1.0.0");
  });

  it("bridges compiled nodes and incremental patches into the NODE-40 renderer-neutral contract", async () => {
    const compiler = new CanvasCompiler({ assetResolver: new AssetResolver(), fontResolver: new FontResolver() });
    const before = document(); const initial = await compiler.compileFull(before); expect(initial.ok).toBe(true); if (!initial.ok) return;
    const canvasScene = compiledSceneToCanvasScene(initial.snapshot);
    expect(canvasScene.orderedIds).toEqual(fixture.orderedIds);
    expect(canvasScene.nodes.get("hero")?.assetId).toBe("asset-hero");
    const after = cloneDocument(before); const nodes = structuredClone(after.nodes) as Record<string, DesignNode>;
    nodes.frame = { ...nodes.frame!, children: ["title", "mask", "badge"] }; delete nodes.hero;
    const update = await compiler.compileIncremental({ previous: initial.snapshot, before, after: { ...after, nodes } });
    expect(update.ok).toBe(true); if (!update.ok) return;
    const calls: string[] = [];
    applyCompiledPatch({
      upsertNode(node) { calls.push(`upsert:${node.id}`); },
      removeNode(id) { calls.push(`remove:${id}`); },
      setPaintOrder(ids) { calls.push(`order:${ids.join(",")}`); },
    }, update.patch);
    expect(calls).toContain("remove:hero");
    expect(calls.at(-1)).toBe("order:frame,title,mask,badge");
  });
});
