import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import vinext from "vinext";
import { cloudflare } from "@cloudflare/vite-plugin";
import { cdnAdapter } from "@vinext/cloudflare/cache/cdn-adapter";

const workerAdapters = {
  name: "tcg-worker-adapters",
  enforce: "pre" as const,
  resolveId(source: string) {
    const normalized = source.replaceAll("\\", "/");
    if (source === "@rate-limit" || normalized.endsWith("/lib/rate-limit.ts")) {
      return fileURLToPath(new URL("./lib/rate-limit.cloudflare.ts", import.meta.url));
    }
    if (source === "@runtime-data" || normalized.endsWith("/lib/runtime-data.ts")) {
      return fileURLToPath(new URL("./lib/runtime-data.cloudflare.ts", import.meta.url));
    }
    return null;
  },
};

export default defineConfig({
  plugins: [
    workerAdapters,
    vinext({
      cache: { cdn: cdnAdapter() },
    }),
    cloudflare({
      viteEnvironment: {
        name: "rsc",
        childEnvironments: ["ssr"],
      },
    }),
  ],
});
