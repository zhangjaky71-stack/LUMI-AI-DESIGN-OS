import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@lumi/artifact-sdk": fileURLToPath(
        new URL("../../packages/artifact-sdk/src/index.ts", import.meta.url),
      ),
      "@lumi/brand-rules": fileURLToPath(
        new URL("../../packages/brand-rules/src/index.ts", import.meta.url),
      ),
      "@lumi/canvas-sdk": fileURLToPath(
        new URL("../../packages/canvas-sdk/src/index.ts", import.meta.url),
      ),
      "@lumi/design-ir": fileURLToPath(
        new URL("../../packages/design-ir/src/index.ts", import.meta.url),
      ),
    },
  },
  test: {
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
