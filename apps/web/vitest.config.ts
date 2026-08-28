import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "@rate-limit": fileURLToPath(new URL("./lib/rate-limit.ts", import.meta.url)),
      "@runtime-data": fileURLToPath(new URL("./lib/runtime-data.ts", import.meta.url)),
      "@": fileURLToPath(new URL(".", import.meta.url))
    }
  },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"]
  }
});
