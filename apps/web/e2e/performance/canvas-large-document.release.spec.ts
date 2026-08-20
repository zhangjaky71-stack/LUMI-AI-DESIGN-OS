import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import { resolve } from "node:path";

interface ProfileF {
  readonly id: "F";
  readonly duration_seconds: number;
  readonly input: {
    readonly reference_device: string;
  };
}

interface Budgets {
  readonly latency_ms: { readonly local_interaction_p95_max: number };
  readonly canvas: {
    readonly fps_target_min: number;
    readonly memory_growth_mb_per_cycle_max: number;
  };
}

interface FrameMetric {
  readonly name: string;
  readonly node_count: number;
  readonly image_heavy: boolean;
  readonly frame_count: number;
  readonly p50_frame_ms: number;
  readonly p95_frame_ms: number;
  readonly mean_frame_ms: number;
  readonly approximate_fps: number;
}

function requireSha(name: string): string {
  const value = process.env[name]?.trim().toLowerCase() ?? "";
  if (!/^[0-9a-f]{40}$/.test(value)) {
    throw new Error(`${name} must be an exact lowercase SHA40`);
  }
  return value;
}

function percentile(values: readonly number[], fraction: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * fraction) - 1)] ?? 0;
}

async function loadJson<T>(path: string): Promise<T> {
  return JSON.parse(await readFile(resolve(process.cwd(), path), "utf8")) as T;
}

const sourceRcSha = requireSha("LUMI_PERF_SOURCE_RC_SHA");
const evidenceHeadSha = requireSha("LUMI_PERF_EVIDENCE_HEAD_SHA");
const baseUrl = new URL(process.env.LUMI_PERF_BASE_URL as string);
const allowedOrigin = baseUrl.origin;

test.describe("NODE-69 / F Canvas Large Document release evidence", () => {
  test.setTimeout(15 * 60 * 1_000);

  test("captures complete Production-like Staging browser evidence", async ({
    browser,
    page,
  }) => {
    const profile = await loadJson<ProfileF>("perf/profiles/v1/F-canvas-large-document.json");
    const budgets = await loadJson<Budgets>("perf/budgets/v1.json");
    const rootPackage = await loadJson<{ devDependencies: Record<string, string> }>("package.json");
    expect(profile.id).toBe("F");
    expect(profile.duration_seconds).toBe(600);
    expect(profile.input.reference_device).toBe("node69-playwright-chromium-swiftshader-v1");

    const startedAt = new Date().toISOString();
    const externalRequests: string[] = [];
    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === allowedOrigin || url.protocol === "data:" || url.protocol === "blob:") {
        await route.continue();
        return;
      }
      externalRequests.push(url.href);
      await route.abort("blockedbyclient");
    });

    await page.addInitScript(() => {
      type PerfState = {
        longTasks: number[];
        lcp: number;
        cls: number;
        eventDurations: number[];
      };
      const state: PerfState = {
        longTasks: [],
        lcp: 0,
        cls: 0,
        eventDurations: [],
      };
      (window as unknown as { __LUMI_RELEASE_PERF__?: PerfState }).__LUMI_RELEASE_PERF__ = state;

      const observe = (type: string, callback: (entry: PerformanceEntry) => void) => {
        try {
          const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) callback(entry);
          });
          observer.observe({ type, buffered: true });
        } catch {
          // The release test fails closed later when a required metric is absent.
        }
      };

      observe("longtask", (entry) => state.longTasks.push(entry.duration));
      observe("largest-contentful-paint", (entry) => {
        state.lcp = Math.max(state.lcp, entry.startTime);
      });
      observe("layout-shift", (entry) => {
        const shift = entry as PerformanceEntry & {
          value?: number;
          hadRecentInput?: boolean;
        };
        if (!shift.hadRecentInput) state.cls += shift.value ?? 0;
      });
      observe("event", (entry) => {
        const event = entry as PerformanceEntry & { interactionId?: number };
        if ((event.interactionId ?? 0) > 0 && event.duration > 0) {
          state.eventDurations.push(event.duration);
        }
      });
    });

    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

    const loadStarted = Date.now();
    await page.goto("/canvas-spike", { waitUntil: "domcontentloaded" });
    try {
      await page.waitForFunction(
        () => window.__LUMI_CANVAS_SPIKE__?.snapshot().ready === true,
        null,
        { timeout: 30_000 },
      );
    } catch (cause) {
      if (externalRequests.length > 0) {
        throw new Error(
          `release browser evidence blocked external runtime dependency: ${[...new Set(externalRequests)].join(", ")}`,
          { cause },
        );
      }
      throw cause;
    }
    const loadMs = Date.now() - loadStarted;
    expect(externalRequests, "release measurement must not depend on external origins").toEqual([]);

    const canvas = page.locator('canvas[data-canvas-spike="pixi"]');
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    if (!box) throw new Error("Pixi release canvas bounding box unavailable");

    const frameMetrics = await page.evaluate(async () => {
      type PixiLike = {
        Application: new () => {
          canvas: HTMLCanvasElement;
          stage: { addChild(value: unknown): void; removeChild(value: unknown): void };
          init(options: Record<string, unknown>): Promise<void>;
          destroy(removeView?: boolean, options?: unknown): void;
        };
        Container: new () => {
          x: number;
          y: number;
          addChild(value: unknown): void;
          destroy(options?: unknown): void;
        };
        Graphics: new () => {
          x: number;
          y: number;
          rect(x: number, y: number, width: number, height: number): unknown;
          fill(color: number): unknown;
        };
        Sprite: new (texture: unknown) => {
          x: number;
          y: number;
          width: number;
          height: number;
        };
        Assets: { load(source: string): Promise<unknown> };
      };
      const pixi = (window as unknown as { PIXI?: PixiLike }).PIXI;
      if (!pixi) throw new Error("Pixi runtime unavailable for NODE-69 benchmark");

      const percentile = (values: readonly number[], fraction: number): number => {
        const sorted = [...values].sort((a, b) => a - b);
        return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * fraction) - 1)] ?? 0;
      };
      const mean = (values: readonly number[]): number =>
        values.reduce((total, value) => total + value, 0) / Math.max(values.length, 1);
      const samples = async (frames: number, onFrame: (index: number) => void): Promise<number[]> => {
        const values: number[] = [];
        let previous = performance.now();
        for (let index = 0; index < frames; index += 1) {
          await new Promise<void>((resolve) => {
            requestAnimationFrame((now) => {
              onFrame(index);
              values.push(now - previous);
              previous = now;
              resolve();
            });
          });
        }
        values.shift();
        return values;
      };
      const metric = (
        name: string,
        nodeCount: number,
        imageHeavy: boolean,
        values: readonly number[],
      ) => {
        const average = mean(values);
        return {
          name,
          node_count: nodeCount,
          image_heavy: imageHeavy,
          frame_count: values.length,
          p50_frame_ms: Number(percentile(values, 0.5).toFixed(3)),
          p95_frame_ms: Number(percentile(values, 0.95).toFixed(3)),
          mean_frame_ms: Number(average.toFixed(3)),
          approximate_fps: Number((1000 / Math.max(average, 0.001)).toFixed(1)),
        };
      };

      const host = document.createElement("div");
      host.style.position = "fixed";
      host.style.left = "0";
      host.style.top = "0";
      host.style.width = "960px";
      host.style.height = "720px";
      host.style.opacity = "0.01";
      host.style.pointerEvents = "none";
      document.body.appendChild(host);
      const app = new pixi.Application();
      await app.init({
        width: 960,
        height: 720,
        background: 0x171717,
        antialias: true,
        autoDensity: false,
        resolution: 1,
        preference: "webgl",
      });
      host.appendChild(app.canvas);

      const measureShapes = async (count: number, name: string) => {
        const root = new pixi.Container();
        for (let index = 0; index < count; index += 1) {
          const graphic = new pixi.Graphics() as unknown as {
            x: number;
            y: number;
            rect(x: number, y: number, width: number, height: number): {
              fill(color: number): unknown;
            };
          };
          graphic.rect(0, 0, 28, 28).fill(0x666666);
          graphic.x = (index % 40) * 32;
          graphic.y = Math.floor(index / 40) * 32;
          root.addChild(graphic);
        }
        app.stage.addChild(root);
        const values = await samples(90, (index) => {
          root.x = -(index % 24) * 3;
          root.y = -(index % 12) * 2;
        });
        app.stage.removeChild(root);
        root.destroy({ children: true });
        return metric(name, count, false, values);
      };

      const productDataUri =
        "data:image/svg+xml;charset=utf-8," +
        encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="56"><rect width="80" height="56" rx="6" fill="#d8b56d"/><circle cx="40" cy="28" r="14" fill="#4f3826"/></svg>');
      const measureImages = async (count: number) => {
        const texture = await pixi.Assets.load(productDataUri);
        const root = new pixi.Container();
        for (let index = 0; index < count; index += 1) {
          const sprite = new pixi.Sprite(texture);
          sprite.width = 80;
          sprite.height = 56;
          sprite.x = (index % 24) * 84;
          sprite.y = Math.floor(index / 24) * 60;
          root.addChild(sprite);
        }
        app.stage.addChild(root);
        const values = await samples(90, (index) => {
          root.x = -(index % 24) * 4;
          root.y = -(index % 12) * 3;
        });
        app.stage.removeChild(root);
        root.destroy({ children: true });
        return metric("image-heavy-1000", count, true, values);
      };

      const result = [
        await measureShapes(500, "simple-500"),
        await measureShapes(1000, "simple-1000"),
        await measureImages(1000),
      ];
      app.destroy(true, { children: true, texture: true, textureSource: true });
      host.remove();
      return result;
    });

    expect(frameMetrics.map((metric) => metric.name)).toEqual([
      "simple-500",
      "simple-1000",
      "image-heavy-1000",
    ]);
    for (const metric of frameMetrics as FrameMetric[]) {
      expect(metric.frame_count).toBeGreaterThan(0);
      expect(metric.p95_frame_ms).toBeGreaterThan(0);
      expect(metric.approximate_fps).toBeGreaterThan(0);
    }

    const zoomLatencies: number[] = [];
    const panLatencies: number[] = [];
    const interactionLatencies: number[] = [];
    const heapSamplesMb: number[] = [];
    const longSessionStarted = Date.now();
    let pageCycle = 0;
    while (Date.now() - longSessionStarted < profile.duration_seconds * 1_000) {
      const zoomStart = Date.now();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.wheel(0, pageCycle % 2 === 0 ? -120 : 120);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      zoomLatencies.push(Date.now() - zoomStart);

      const panStart = Date.now();
      await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.55);
      await page.mouse.down({ button: "middle" });
      await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.58, { steps: 2 });
      await page.mouse.up({ button: "middle" });
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      panLatencies.push(Date.now() - panStart);

      const interactionStart = Date.now();
      await page.mouse.click(box.x + 400, box.y + 528);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      interactionLatencies.push(Date.now() - interactionStart);

      const heapMb = await page.evaluate(() => {
        const memory = (performance as Performance & {
          memory?: { usedJSHeapSize?: number };
        }).memory;
        const used = memory?.usedJSHeapSize;
        if (!Number.isFinite(used)) return null;
        return (used as number) / 1024 / 1024;
      });
      if (heapMb === null) throw new Error("precise Chromium heap telemetry unavailable");
      heapSamplesMb.push(heapMb);

      pageCycle += 1;
      const elapsed = Date.now() - longSessionStarted;
      const remaining = profile.duration_seconds * 1_000 - elapsed;
      if (remaining > 0) await page.waitForTimeout(Math.min(5_000, remaining));
    }
    expect(pageCycle).toBeGreaterThanOrEqual(100);

    await page.mouse.click(box.x + 400, box.y + 528);
    await page.waitForTimeout(250);

    const browserTelemetry = await page.evaluate(() => {
      type PerfState = {
        longTasks: number[];
        lcp: number;
        cls: number;
        eventDurations: number[];
      };
      const state = (window as unknown as { __LUMI_RELEASE_PERF__?: PerfState }).__LUMI_RELEASE_PERF__;
      if (!state) throw new Error("browser performance observer state unavailable");
      const canvas = document.querySelector('canvas[data-canvas-spike="pixi"]') as HTMLCanvasElement | null;
      if (!canvas) throw new Error("Pixi canvas unavailable for WebGL provenance");
      const gl = (canvas.getContext("webgl2") || canvas.getContext("webgl")) as WebGLRenderingContext | null;
      if (!gl) throw new Error("WebGL context unavailable");
      const debug = gl.getExtension("WEBGL_debug_renderer_info");
      const webglVendor = debug ? String(gl.getParameter(debug.UNMASKED_VENDOR_WEBGL)) : String(gl.getParameter(gl.VENDOR));
      const webglRenderer = debug ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER));
      return {
        user_agent: navigator.userAgent,
        webgl_vendor: webglVendor,
        webgl_renderer: webglRenderer,
        long_tasks_ms: state.longTasks,
        lcp_ms: state.lcp,
        cls: state.cls,
        event_durations_ms: state.eventDurations,
      };
    });

    if (browserTelemetry.lcp_ms <= 0) throw new Error("LCP evidence unavailable");
    if (browserTelemetry.event_durations_ms.length === 0) throw new Error("INP/Event Timing evidence unavailable");
    if (heapSamplesMb.length < 2) throw new Error("long-session heap evidence incomplete");

    const fps = Math.min(...frameMetrics.map((metric) => metric.approximate_fps));
    const heapGrowthPerCycleMb =
      (heapSamplesMb[heapSamplesMb.length - 1]! - heapSamplesMb[0]!) /
      Math.max(1, heapSamplesMb.length - 1);
    const measurements = {
      fps: {
        min_across_required_scenarios: fps,
        target_min: budgets.canvas.fps_target_min,
        scenarios: frameMetrics,
      },
      long_tasks: {
        count: browserTelemetry.long_tasks_ms.length,
        max_ms: Math.max(0, ...browserTelemetry.long_tasks_ms),
        total_ms: browserTelemetry.long_tasks_ms.reduce((sum, value) => sum + value, 0),
      },
      heap_memory_mb: {
        first: heapSamplesMb[0],
        last: heapSamplesMb[heapSamplesMb.length - 1],
        max: Math.max(...heapSamplesMb),
        growth_per_cycle: heapGrowthPerCycleMb,
        target_growth_per_cycle_max: budgets.canvas.memory_growth_mb_per_cycle_max,
        samples: heapSamplesMb.length,
      },
      load_ms: loadMs,
      zoom_latency_ms: {
        p95: percentile(zoomLatencies, 0.95),
        samples: zoomLatencies.length,
      },
      pan_latency_ms: {
        p95: percentile(panLatencies, 0.95),
        samples: panLatencies.length,
      },
      interaction_latency_ms: {
        p95: percentile(interactionLatencies, 0.95),
        target_p95_max: budgets.latency_ms.local_interaction_p95_max,
        samples: interactionLatencies.length,
      },
      lcp_ms: browserTelemetry.lcp_ms,
      inp_ms: percentile(browserTelemetry.event_durations_ms, 0.98),
      cls: browserTelemetry.cls,
    };

    const finishedAt = new Date().toISOString();
    const cpus = os.cpus();
    const result = {
      schema_version: 1,
      kind: "node69_browser_canvas_release_evidence",
      profile_id: "F",
      reference_device: profile.input.reference_device,
      environment: "production_like_staging",
      source_rc_sha: sourceRcSha,
      evidence_head_sha: evidenceHeadSha,
      base_url: allowedOrigin,
      playwright_version: rootPackage.devDependencies["@playwright/test"],
      browser_version: browser?.version() ?? page.context().browser()?.version() ?? "unknown",
      user_agent: browserTelemetry.user_agent,
      os: `${os.platform()}-${os.release()}`,
      architecture: os.arch(),
      cpu_model: cpus[0]?.model ?? "unknown",
      logical_cpu_count: cpus.length,
      memory_total_bytes: os.totalmem(),
      webgl_vendor: browserTelemetry.webgl_vendor,
      webgl_renderer: browserTelemetry.webgl_renderer,
      viewport: { width: 1440, height: 900 },
      device_scale_factor: 1,
      cpu_throttle_rate: 4,
      long_session_seconds: profile.duration_seconds,
      multi_page_cycles: pageCycle,
      external_requests: externalRequests,
      measurements,
      started_at: startedAt,
      finished_at: finishedAt,
    };

    for (const key of [
      "fps",
      "long_tasks",
      "heap_memory_mb",
      "load_ms",
      "zoom_latency_ms",
      "pan_latency_ms",
      "interaction_latency_ms",
      "lcp_ms",
      "inp_ms",
      "cls",
    ]) {
      if (!(key in measurements)) throw new Error(`required F metric missing: ${key}`);
    }
    expect(result.external_requests).toEqual([]);
    expect(result.long_session_seconds).toBe(600);
    expect(result.multi_page_cycles).toBeGreaterThanOrEqual(100);

    const outputDir = resolve(process.cwd(), "perf/results/node-69-release");
    await mkdir(outputDir, { recursive: true });
    await writeFile(
      resolve(outputDir, "browser-canvas-F.json"),
      `${JSON.stringify(result, null, 2)}\n`,
      "utf8",
    );
    await cdp.detach();
  });
});
