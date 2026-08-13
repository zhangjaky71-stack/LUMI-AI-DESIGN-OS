"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import styles from "./canvas-spike.module.css";
import {
  CanvasSpikeRuntime,
  PIXI_CDN_URL,
  PIXI_VERSION,
  type CanvasSpikeBenchmarkReport,
  type CanvasSpikeSnapshot,
  type TextEditorRequest,
} from "./pixi-runtime";

const EMPTY_SNAPSHOT: CanvasSpikeSnapshot = {
  ready: false,
  renderer: "not-ready",
  pixiVersion: PIXI_VERSION,
  camera: { x: 0, y: 0, zoom: 1 },
  selectedIds: [],
  selectionRect: null,
  marqueeRect: null,
  selectedImageRef: null,
  nodeCount: 0,
  visibleNodeCount: 0,
  history: { canUndo: false, canRedo: false },
};

function formatMetric(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "—";
}

export default function CanvasSpikeClient() {
  const hostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<CanvasSpikeRuntime | null>(null);
  const [scriptReady, setScriptReady] = useState(false);
  const [snapshot, setSnapshot] = useState<CanvasSpikeSnapshot>(EMPTY_SNAPSHOT);
  const [textEditor, setTextEditor] = useState<TextEditorRequest | null>(null);
  const [draftText, setDraftText] = useState("");
  const [isComposing, setIsComposing] = useState(false);
  const [benchmark, setBenchmark] = useState<CanvasSpikeBenchmarkReport | null>(
    null,
  );
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scriptReady || !hostRef.current || runtimeRef.current) {
      return;
    }
    const runtime = new CanvasSpikeRuntime({
      host: hostRef.current,
      onSnapshot: setSnapshot,
      onTextEdit: (request) => {
        setTextEditor(request);
        setDraftText(request?.text ?? "");
      },
    });
    runtimeRef.current = runtime;
    void runtime.init().catch((cause: unknown) => {
      setError(
        cause instanceof Error ? cause.message : "Canvas Spike 初始化失败",
      );
    });
    return () => {
      runtime.dispose();
      runtimeRef.current = null;
    };
  }, [scriptReady]);

  const runBenchmark = async () => {
    const runtime = runtimeRef.current;
    if (!runtime || benchmarkRunning) {
      return;
    }
    setBenchmarkRunning(true);
    setError(null);
    try {
      setBenchmark(await runtime.runBenchmark());
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Benchmark 失败");
    } finally {
      setBenchmarkRunning(false);
    }
  };

  const commitText = () => {
    if (!textEditor || isComposing) {
      return;
    }
    runtimeRef.current?.commitText(textEditor.nodeId, draftText);
  };

  const beginResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    const handle = event.currentTarget.dataset.resizeHandle;
    if (
      handle !== "nw" &&
      handle !== "ne" &&
      handle !== "sw" &&
      handle !== "se"
    ) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    runtimeRef.current?.beginResize(handle, event.nativeEvent);
  };

  const beginRotate = (event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();
    runtimeRef.current?.beginRotate(event.nativeEvent);
  };

  return (
    <main className={styles.page}>
      <Script
        src={PIXI_CDN_URL}
        strategy="afterInteractive"
        onLoad={() => setScriptReady(true)}
        onError={() => setError(`无法加载 PixiJS ${PIXI_VERSION}`)}
      />

      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>NODE-08 / Canvas Technology Spike</p>
          <h1>PixiJS Infinite Canvas Spike</h1>
        </div>
        <div className={styles.statusRow}>
          <span className={styles.pill}>Pixi {snapshot.pixiVersion}</span>
          <span className={styles.pill}>{snapshot.renderer}</span>
          <span className={styles.pill}>
            Zoom {(snapshot.camera.zoom * 100).toFixed(0)}%
          </span>
          <span className={snapshot.ready ? styles.ready : styles.pending}>
            {snapshot.ready ? "READY" : "LOADING"}
          </span>
        </div>
      </header>

      <section className={styles.workspace}>
        <aside className={styles.sidebar}>
          <h2>Spike Controls</h2>
          <p className={styles.help}>
            Wheel/trackpad zoom-to-cursor · Space/middle drag pan · Shift
            multi-select · drag nodes · double-click text · Ctrl/Cmd C/V/Z/Y.
          </p>

          <div className={styles.buttonGrid}>
            <button
              type="button"
              onClick={() => runtimeRef.current?.undo()}
              disabled={!snapshot.history.canUndo}
            >
              Undo
            </button>
            <button
              type="button"
              onClick={() => runtimeRef.current?.redo()}
              disabled={!snapshot.history.canRedo}
            >
              Redo
            </button>
            <button
              type="button"
              onClick={() => runtimeRef.current?.copySelection()}
              disabled={snapshot.selectedIds.length === 0}
            >
              Copy
            </button>
            <button
              type="button"
              onClick={() => runtimeRef.current?.pasteSelection()}
            >
              Paste
            </button>
            <button
              type="button"
              onClick={() => runtimeRef.current?.reorderSelection(-1)}
              disabled={snapshot.selectedIds.length === 0}
            >
              Layer −
            </button>
            <button
              type="button"
              onClick={() => runtimeRef.current?.reorderSelection(1)}
              disabled={snapshot.selectedIds.length === 0}
            >
              Layer +
            </button>
          </div>

          <dl className={styles.stats}>
            <div>
              <dt>Scene nodes</dt>
              <dd>{snapshot.nodeCount}</dd>
            </div>
            <div>
              <dt>Visible after cull</dt>
              <dd>{snapshot.visibleNodeCount}</dd>
            </div>
            <div>
              <dt>Selection</dt>
              <dd>{snapshot.selectedIds.length}</dd>
            </div>
            <div>
              <dt>Camera world</dt>
              <dd>
                {snapshot.camera.x.toFixed(0)}, {snapshot.camera.y.toFixed(0)}
              </dd>
            </div>
          </dl>

          <div
            className={styles.referenceCard}
            data-testid="selected-reference"
          >
            <span>Selected image reference</span>
            <strong>{snapshot.selectedImageRef ?? "—"}</strong>
          </div>

          <button
            type="button"
            className={styles.benchmarkButton}
            onClick={() => void runBenchmark()}
            disabled={!snapshot.ready || benchmarkRunning}
            data-testid="run-benchmark"
          >
            {benchmarkRunning ? "Running…" : "Run 2k / 10k benchmark"}
          </button>

          {error ? <p className={styles.error}>{error}</p> : null}
        </aside>

        <div className={styles.canvasColumn}>
          <div className={styles.canvasShell} data-testid="canvas-shell">
            <div ref={hostRef} className={styles.canvasHost} />

            {snapshot.marqueeRect ? (
              <div
                className={styles.marquee}
                style={{
                  left: snapshot.marqueeRect.x,
                  top: snapshot.marqueeRect.y,
                  width: snapshot.marqueeRect.width,
                  height: snapshot.marqueeRect.height,
                }}
              />
            ) : null}

            {snapshot.selectionRect ? (
              <div
                className={styles.selectionBox}
                style={{
                  left: snapshot.selectionRect.x,
                  top: snapshot.selectionRect.y,
                  width: snapshot.selectionRect.width,
                  height: snapshot.selectionRect.height,
                }}
                data-testid="selection-box"
              >
                <button
                  className={`${styles.handle} ${styles.nw}`}
                  data-resize-handle="nw"
                  onPointerDown={beginResize}
                  aria-label="resize northwest"
                />
                <button
                  className={`${styles.handle} ${styles.ne}`}
                  data-resize-handle="ne"
                  onPointerDown={beginResize}
                  aria-label="resize northeast"
                />
                <button
                  className={`${styles.handle} ${styles.sw}`}
                  data-resize-handle="sw"
                  onPointerDown={beginResize}
                  aria-label="resize southwest"
                />
                <button
                  className={`${styles.handle} ${styles.se}`}
                  data-resize-handle="se"
                  onPointerDown={beginResize}
                  aria-label="resize southeast"
                />
                <button
                  className={styles.rotateHandle}
                  onPointerDown={beginRotate}
                  aria-label="rotate selection"
                >
                  ↻
                </button>
              </div>
            ) : null}

            {textEditor ? (
              <textarea
                className={styles.textEditor}
                style={{
                  left: textEditor.rect.x,
                  top: textEditor.rect.y,
                  width: Math.max(160, textEditor.rect.width),
                  height: Math.max(90, textEditor.rect.height),
                }}
                value={draftText}
                onChange={(event) => setDraftText(event.target.value)}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                onBlur={commitText}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    (event.ctrlKey || event.metaKey) &&
                    !isComposing
                  ) {
                    commitText();
                  }
                }}
                data-testid="dom-text-editor"
                data-ime-safe="true"
                autoFocus
              />
            ) : null}
          </div>
          <p className={styles.caption}>
            Pixi Scene Graph is disposable renderer state. Camera coordinates,
            selection, undo/redo and asset references live outside Pixi in{" "}
            <code>@lumi/canvas-sdk</code>.
          </p>
        </div>

        <aside className={styles.benchmarkPanel}>
          <h2>Measured Browser Signal</h2>
          <p className={styles.help}>
            CI headless Chromium is used as a reproducible regression signal. It
            is not treated as final workstation/GPU certification.
          </p>
          {benchmark ? (
            <>
              <p className={styles.benchmarkMeta}>
                {benchmark.renderer} · DPR {benchmark.devicePixelRatio} ·{" "}
                {benchmark.pixiVersion}
              </p>
              <div
                className={styles.metricList}
                data-testid="benchmark-results"
              >
                {benchmark.metrics.map((metric) => (
                  <article key={metric.name}>
                    <strong>{metric.name}</strong>
                    <span>{metric.nodeCount.toLocaleString()} nodes</span>
                    <span>P50 {formatMetric(metric.p50FrameMs)} ms</span>
                    <span>P95 {formatMetric(metric.p95FrameMs)} ms</span>
                    <span>~{formatMetric(metric.approximateFps)} fps</span>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className={styles.placeholder}>
              Run benchmark to populate actual browser frame metrics.
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
