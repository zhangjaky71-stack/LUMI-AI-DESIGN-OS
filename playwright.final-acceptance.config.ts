import { defineConfig, devices } from "@playwright/test";

const finalAcceptanceSpecs = [
  "app-shell.spec.ts",
  "projects.spec.ts",
  "ai-workspace.spec.ts",
  "canvas-engine.spec.ts",
  "layers-inspector.spec.ts",
  "versions-ui.spec.ts",
  "export-ui.spec.ts",
  "billing.spec.ts",
  "final-accessibility-preflight.spec.ts",
];

export default defineConfig({
  testDir: "./apps/web/e2e",
  testMatch: finalAcceptanceSpecs,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [["line"]],
  outputDir: "test-results/final-browser-acceptance",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chrome-stable",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
    {
      name: "edge-stable",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
    {
      name: "firefox-engine",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      // WebKit is an automated Safari-engine preflight. It is not accepted as
      // proof that real macOS Safari BROWSER-02 has passed.
      name: "webkit-safari-engine-preflight",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: {
    command: "pnpm --filter @lumi/web dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
  },
});
