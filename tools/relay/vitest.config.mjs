import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

const TEST_SECRET = "s".repeat(64);
process.env.RELAY_SECRET ??= TEST_SECRET;

export default defineConfig({
  plugins: [
    cloudflareTest({
      miniflare: {
        bindings: { RELAY_SECRET: TEST_SECRET },
      },
      wrangler: { configPath: "./wrangler.test.jsonc" },
    }),
  ],
  test: {
    include: ["mailbox.vitest.mjs"],
  },
});
