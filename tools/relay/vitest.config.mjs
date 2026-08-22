import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

const TEST_SECRET = "s".repeat(64);

export default defineConfig({
  plugins: [
    cloudflareTest({
      miniflare: {
        bindings: { RELAY_SECRET: TEST_SECRET },
      },
      wrangler: { configPath: "./wrangler.jsonc" },
    }),
  ],
  test: {
    include: ["mailbox.vitest.mjs"],
  },
});
