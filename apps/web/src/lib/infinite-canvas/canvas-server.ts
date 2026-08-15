import type { DesignDocument } from "@lumi/design-ir";
import type { InfiniteCanvasBootstrap, InfiniteCanvasSeed } from "./types";

function designDocument(projectId: string): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: `document:${projectId}`,
    unit: "px",
    root_id: "root",
    nodes: {
      root: {
        id: "root",
        kind: "DOCUMENT_ROOT",
        name: "Campaign Canvas",
        parent_id: null,
        children: ["frame-square", "frame-feed", "frame-story"],
      },
      "frame-square": {
        id: "frame-square",
        kind: "FRAME",
        name: "Square / 1:1",
        parent_id: "root",
        children: ["node-hero-product", "node-headline", "node-offer"],
        transform: { x: 0, y: 0, width: 1080, height: 1080 },
        metadata: { preset: "1:1", fill: "#ece7dd" },
      },
      "node-hero-product": {
        id: "node-hero-product",
        kind: "IMAGE",
        name: "Hero Product",
        parent_id: "frame-square",
        children: [],
        locked: true,
        asset_id: "asset-lumi-product",
        transform: { x: 470, y: 245, width: 470, height: 610 },
        metadata: { role: "product", identity: "locked" },
      },
      "node-headline": {
        id: "node-headline",
        kind: "TEXT",
        name: "Headline",
        parent_id: "frame-square",
        children: [],
        content: "SUMMER\nSIGNATURE",
        transform: { x: 90, y: 110, width: 520, height: 180 },
        metadata: { fill: "#17191c", font_size: 72 },
      },
      "node-offer": {
        id: "node-offer",
        kind: "SHAPE",
        name: "Offer Badge",
        parent_id: "frame-square",
        children: [],
        transform: { x: 90, y: 800, width: 260, height: 110 },
        metadata: { fill: "#1d2024", label: "NEW  /  39" },
      },
      "frame-feed": {
        id: "frame-feed",
        kind: "FRAME",
        name: "Feed / 4:5",
        parent_id: "root",
        children: ["feed-image", "feed-title"],
        transform: { x: 1320, y: 0, width: 1080, height: 1350 },
        metadata: { preset: "4:5", fill: "#181a1e" },
      },
      "feed-image": {
        id: "feed-image",
        kind: "IMAGE",
        name: "Product Crop",
        parent_id: "frame-feed",
        children: [],
        asset_id: "asset-lumi-product",
        transform: { x: 390, y: 280, width: 560, height: 720 },
        metadata: { role: "product" },
      },
      "feed-title": {
        id: "feed-title",
        kind: "TEXT",
        name: "Feed Headline",
        parent_id: "frame-feed",
        children: [],
        content: "LIGHT / ROAST / SUMMER",
        transform: { x: 90, y: 95, width: 760, height: 90 },
        metadata: { fill: "#f4f1ea", font_size: 54 },
      },
      "frame-story": {
        id: "frame-story",
        kind: "FRAME",
        name: "Story / 9:16",
        parent_id: "root",
        children: ["story-title", "story-accent"],
        transform: { x: 2640, y: 0, width: 1080, height: 1920 },
        metadata: { preset: "9:16", fill: "#d9d1c4" },
      },
      "story-title": {
        id: "story-title",
        kind: "TEXT",
        name: "Story Headline",
        parent_id: "frame-story",
        children: [],
        content: "A NEW\nSUMMER\nRITUAL",
        transform: { x: 100, y: 180, width: 620, height: 360 },
        metadata: { fill: "#141619", font_size: 78 },
      },
      "story-accent": {
        id: "story-accent",
        kind: "SHAPE",
        name: "Accent",
        parent_id: "frame-story",
        children: [],
        transform: { x: 100, y: 1420, width: 680, height: 260 },
        metadata: { fill: "#24272b", label: "SEASON 06" },
      },
    },
    resources: {},
    metadata: { document_version: 7, project_id: projectId },
  };
}

function seed(projectId: string): InfiniteCanvasSeed {
  return {
    snapshot: {
      project_id: projectId,
      document: designDocument(projectId),
      saved_at: "2026-08-15T03:10:00.000Z",
    },
    conflict_on_next_save: projectId === "project-canvas-conflict",
  };
}

export function getInfiniteCanvasBootstrap(projectId: string): InfiniteCanvasBootstrap {
  const e2e = process.env.NODE_ENV !== "production" && process.env.LUMI_INFINITE_CANVAS_E2E === "1";
  return e2e ? { mode: "e2e", seed: seed(projectId) } : { mode: "http", seed: null };
}
