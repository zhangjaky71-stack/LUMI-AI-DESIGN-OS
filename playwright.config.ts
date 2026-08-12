import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./apps/web/e2e",
  use: { baseURL: "http://127.0.0.1:3000", trace: "on-first-retry" },
  webServer: {
    command: "pnpm --filter @lumi/web dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
  },
});
