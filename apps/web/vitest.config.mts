import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Inline (empty) PostCSS config, so Vite does not load the Next-only Tailwind pipeline.
  css: { postcss: { plugins: [] } },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    // Pure lib functions run in node; component tests opt into jsdom per file.
    environment: "node",
    include: ["test/**/*.test.ts", "test/**/*.test.tsx"],
    setupFiles: ["./test/setup.ts"],
  },
});
