"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import {
  CanvasController,
  PixiV8RendererAdapter,
  createPixiV8Bindings,
  type PixiApplicationHost,
  type PixiContainerLike,
  type PixiV8RuntimeModule,
} from "@lumi/canvas-sdk";
import { reportCanvasError } from "../../lib/observability/browser";
import { PIXI_CDN_URL } from "../canvas-spike/pixi-runtime";

type CanvasDocument = ConstructorParameters<typeof CanvasController>[0];
type CanvasConstraint = Parameters<CanvasController["setConstraints"]>[0][number];

interface BrowserPixiApplication {
  readonly canvas: HTMLCanvasElement;
  readonly stage: PixiContainerLike;
  readonly renderer: { resize(width: number, height: number): void };
  init(options: Record<string, unknown>): Promise<void>;
  destroy(removeView?: boolean, options?: unknown): void;
}

interface BrowserPixiRuntime extends PixiV8RuntimeModule {
  readonly VERSION?: string;
  readonly Application: new () => BrowserPixiApplication;
}

interface BrowserHarnessSnapshot {
  readonly ready: boolean;
  readonly shape_x: number;
  readonly document_version: number;
  readonly camera_x: number;
  readonly last_decision: string;
}

declare global {
  interface Window {
    __LUMI_CANVAS_ENGINE__?: {
      snapshot(): BrowserHarnessSnapshot;
      moveShape(dx: number): boolean;
      lockAndMove(dx: number): boolean;
      pan(dx: number): void;
    };
  }
}

function documentFixture(): CanvasDocument {
  return {
    schema_version: "1.0",
    document_id: "browser-canvas-engine",
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
        children: ["title", "shape"],
        transform: { x: 120, y: 80, width: 520, height: 360 },
        metadata: { fill: 0xf6f4ef },
      },
      title: {
        id: "title",
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content: "LUMI Canvas Engine",
        transform: { x: 36, y: 32, width: 300, height: 40 },
      },
      shape: {
        id: "shape",
        kind: "SHAPE",
        parent_id: "frame",
        children: [],
        transform: { x: 80, y: 120, width: 160, height: 100 },
        metadata: { fill: 0x222222 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

function positionLock(version: number): CanvasConstraint {
  return {
    id: "browser-lock-shape",
    type: "LOCK_POSITION",
    scope: { node_ids: ["shape"] },
    severity: "HARD",
    source: "USER_EXPLICIT",
    priority: 1000,
    parameters: {},
    active: true,
    document_version: version,
  };
}

export default function CanvasEngineClient() {
  const hostRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<CanvasController | null>(null);
  const decisionRef = useRef("NOT_READY");
  const [scriptReady, setScriptReady] = useState(false);
  const [ready, setReady] = useState(false);
  const [decision, setDecision] = useState("NOT_READY");
  const [snapshot, setSnapshot] = useState<BrowserHarnessSnapshot>({
    ready: false,
    shape_x: 0,
    document_version: 0,
    camera_x: 0,
    last_decision: "NOT_READY",
  });

  useEffect(() => {
    if (!scriptReady || !hostRef.current || controllerRef.current) return;
    let disposed = false;
    const hostElement = hostRef.current;
    const initialize = async () => {
      const pixi = (window as unknown as { PIXI?: BrowserPixiRuntime }).PIXI;
      if (!pixi) throw new Error("PixiJS global unavailable");
      const app = new pixi.Application();
      await app.init({
        width: hostElement.clientWidth || 900,
        height: hostElement.clientHeight || 600,
        background: 0x171717,
        antialias: true,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        preference: "webgl",
      });
      if (disposed) {
        app.destroy(true, { children: true });
        return;
      }
      app.canvas.dataset.canvasEngine = "pixi";
      app.canvas.style.width = "100%";
      app.canvas.style.height = "100%";
      app.canvas.style.display = "block";
      hostElement.replaceChildren(app.canvas);

      const appHost: PixiApplicationHost = {
        stage: app.stage,
        resize(widthCssPx, heightCssPx) {
          app.renderer.resize(Math.max(1, widthCssPx), Math.max(1, heightCssPx));
        },
        destroy() {
          app.destroy(true, { children: true, texture: true, textureSource: true });
        },
      };
      const bindings = createPixiV8Bindings(pixi, appHost, {
        textureForAsset: () => null,
      });
      const renderer = new PixiV8RendererAdapter(bindings);
      const controller = new CanvasController(documentFixture(), {
        renderer,
        initial_viewport: {
          width: hostElement.clientWidth || 900,
          height: hostElement.clientHeight || 600,
        },
      });
      controllerRef.current = controller;
      controller.fitAll(40);
      controller.renderNow();

      const readSnapshot = (): BrowserHarnessSnapshot => {
        const state = controller.snapshot();
        return {
          ready: true,
          shape_x: state.document.nodes.shape?.transform?.x ?? 0,
          document_version:
            typeof state.document.metadata.document_version === "number"
              ? state.document.metadata.document_version
              : 0,
          camera_x: state.camera.x,
          last_decision: decisionRef.current,
        };
      };
      const publish = (nextDecision: string) => {
        decisionRef.current = nextDecision;
        setDecision(nextDecision);
        const next = { ...readSnapshot(), last_decision: nextDecision };
        setSnapshot(next);
        return next;
      };

      window.__LUMI_CANVAS_ENGINE__ = {
        snapshot: readSnapshot,
        moveShape(dx) {
          controller.setConstraints([]);
          controller.selection.set(["shape"]);
          const session = controller.beginTransform("browser-move");
          session.previewMove(dx, 0);
          const result = controller.commitTransform(session, "browser-move");
          publish(result.guarded.preflight.decision);
          return result.accepted;
        },
        lockAndMove(dx) {
          const version = readSnapshot().document_version;
          controller.setConstraints([positionLock(version)]);
          controller.selection.set(["shape"]);
          const session = controller.beginTransform("browser-locked-move");
          session.previewMove(dx, 0);
          const result = controller.commitTransform(session, "browser-locked-move");
          publish(result.guarded.preflight.decision);
          return result.accepted;
        },
        pan(dx) {
          controller.pan({ x: dx, y: 0 });
          controller.renderNow();
          publish("CAMERA");
        },
      };
      setReady(true);
      publish("ALLOW");
    };

    void initialize().catch((error: unknown) => {
      reportCanvasError("canvas_initialization_failed");
      const message = error instanceof Error ? error.message : "Canvas initialization failed";
      decisionRef.current = `ERROR:${message}`;
      setDecision(decisionRef.current);
    });

    return () => {
      disposed = true;
      delete window.__LUMI_CANVAS_ENGINE__;
      controllerRef.current?.destroy();
      controllerRef.current = null;
    };
  }, [scriptReady]);

  return (
    <main style={{ minHeight: "100vh", background: "#0f0f0f", color: "white", padding: 24 }}>
      <Script src={PIXI_CDN_URL} strategy="afterInteractive" onLoad={() => setScriptReady(true)} />
      <header style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>NODE-40 Canvas Engine</h1>
          <p style={{ margin: "6px 0 0", opacity: 0.65 }}>
            Design IR → Constraint → PixiJS v8
          </p>
        </div>
        <div data-testid="canvas-engine-status">{ready ? "READY" : decision}</div>
      </header>
      <div
        ref={hostRef}
        data-testid="canvas-engine-host"
        style={{
          width: "100%",
          height: 620,
          border: "1px solid #333",
          borderRadius: 12,
          overflow: "hidden",
        }}
      />
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <div>
          <dt>Shape X</dt>
          <dd data-testid="shape-x">{snapshot.shape_x}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd data-testid="document-version">{snapshot.document_version}</dd>
        </div>
        <div>
          <dt>Camera X</dt>
          <dd data-testid="camera-x">{snapshot.camera_x.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Decision</dt>
          <dd data-testid="constraint-decision">{snapshot.last_decision}</dd>
        </div>
      </dl>
    </main>
  );
}
