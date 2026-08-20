import { defineConfig } from "@playwright/test";

function releaseBaseUrl(): string {
  const raw = process.env.LUMI_PERF_BASE_URL?.trim();
  if (!raw) {
    throw new Error("LUMI_PERF_BASE_URL is required for release performance evidence");
  }
  const url = new URL(raw);
  if (url.protocol !== "https:") {
    throw new Error("release performance target must use https");
  }
  const host = url.hostname.toLowerCase();
  if (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host.endsWith(".localhost")
  ) {
    throw new Error("loopback/local targets cannot produce release performance evidence");
  }
  return url.origin;
}

const baseURL = releaseBaseUrl();

export default defineConfig({
  testDir: "./apps/web/e2e/performance",
  testMatch: "**/*.release.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 15 * 60 * 1_000,
  expect: { timeout: 15_000 },
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    locale: "en-US",
    timezoneId: "UTC",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: {
      args: [
        "--use-angle=swiftshader",
        "--disable-features=Vulkan",
        "--enable-precise-memory-info",
      ],
    },
  },
});
