import type { Page } from "@playwright/test";

export async function installNode69MultiPageHarness(page: Page): Promise<void> {
  await page.evaluate(async () => {
    type Display = { x: number; y: number; visible: boolean };
    type Container = Display & {
      addChild(value: unknown): void;
      destroy(options?: unknown): void;
    };
    type PixiLike = {
      Application: new () => {
        canvas: HTMLCanvasElement;
        stage: { addChild(value: unknown): void };
        init(options: Record<string, unknown>): Promise<void>;
        destroy(removeView?: boolean, options?: unknown): void;
      };
      Container: new () => Container;
      Graphics: new () => {
        x: number;
        y: number;
        rect(x: number, y: number, width: number, height: number): {
          fill(color: number): unknown;
        };
      };
    };
    type Harness = {
      cycle(): Promise<{ page_index: number; latency_ms: number }>;
      destroy(): void;
      readonly page_count: number;
      readonly node_count: number;
    };

    const scopedWindow = window as unknown as {
      PIXI?: PixiLike;
      __LUMI_NODE69_MULTI_PAGE__?: Harness;
    };
    if (scopedWindow.__LUMI_NODE69_MULTI_PAGE__) {
      throw new Error("NODE-69 multi-page harness already installed");
    }
    const pixi = scopedWindow.PIXI;
    if (!pixi) throw new Error("Pixi runtime unavailable for multi-page harness");

    const host = document.createElement("div");
    host.dataset.node69MultiPageHarness = "true";
    host.style.position = "fixed";
    host.style.left = "0";
    host.style.bottom = "0";
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

    const pageCount = 4;
    const nodesPerPage = 250;
    const pages: Container[] = [];
    for (let pageIndex = 0; pageIndex < pageCount; pageIndex += 1) {
      const pageRoot = new pixi.Container();
      pageRoot.visible = pageIndex === 0;
      for (let index = 0; index < nodesPerPage; index += 1) {
        const graphic = new pixi.Graphics();
        graphic.rect(0, 0, 34, 34).fill(0x555555 + pageIndex * 0x080808);
        graphic.x = (index % 25) * 38;
        graphic.y = Math.floor(index / 25) * 38;
        pageRoot.addChild(graphic);
      }
      app.stage.addChild(pageRoot);
      pages.push(pageRoot);
    }

    let cycleIndex = 0;
    scopedWindow.__LUMI_NODE69_MULTI_PAGE__ = {
      page_count: pageCount,
      node_count: pageCount * nodesPerPage,
      async cycle() {
        const started = performance.now();
        const active = cycleIndex % pageCount;
        for (let index = 0; index < pages.length; index += 1) {
          const candidate = pages[index];
          if (!candidate) continue;
          candidate.visible = index === active;
          if (candidate.visible) {
            candidate.x = -((cycleIndex % 20) * 3);
            candidate.y = -((cycleIndex % 10) * 2);
          }
        }
        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        cycleIndex += 1;
        return {
          page_index: active,
          latency_ms: performance.now() - started,
        };
      },
      destroy() {
        for (const pageRoot of pages) pageRoot.destroy({ children: true });
        app.destroy(true, { children: true, texture: true, textureSource: true });
        host.remove();
        delete scopedWindow.__LUMI_NODE69_MULTI_PAGE__;
      },
    };
  });
}

export async function cycleNode69MultiPageHarness(
  page: Page,
): Promise<{ page_index: number; latency_ms: number }> {
  return page.evaluate(async () => {
    const harness = (window as unknown as {
      __LUMI_NODE69_MULTI_PAGE__?: {
        cycle(): Promise<{ page_index: number; latency_ms: number }>;
      };
    }).__LUMI_NODE69_MULTI_PAGE__;
    if (!harness) throw new Error("NODE-69 multi-page harness is not installed");
    return harness.cycle();
  });
}

export async function readNode69MultiPageShape(
  page: Page,
): Promise<{ page_count: number; node_count: number }> {
  return page.evaluate(() => {
    const harness = (window as unknown as {
      __LUMI_NODE69_MULTI_PAGE__?: {
        readonly page_count: number;
        readonly node_count: number;
      };
    }).__LUMI_NODE69_MULTI_PAGE__;
    if (!harness) throw new Error("NODE-69 multi-page harness is not installed");
    return {
      page_count: harness.page_count,
      node_count: harness.node_count,
    };
  });
}

export async function destroyNode69MultiPageHarness(page: Page): Promise<void> {
  await page.evaluate(() => {
    const harness = (window as unknown as {
      __LUMI_NODE69_MULTI_PAGE__?: { destroy(): void };
    }).__LUMI_NODE69_MULTI_PAGE__;
    harness?.destroy();
  });
}
