import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Mirror the tsconfig "@/*" -> project-root alias without the ESM-only paths plugin.
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
  },
});
