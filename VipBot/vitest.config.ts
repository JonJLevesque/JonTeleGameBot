import path from "node:path";
import { defineConfig } from "vitest/config";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";

const migrations = await readD1Migrations(path.join(import.meta.dirname, "migrations"));

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml" },
      miniflare: {
        bindings: {
          TG_BOT_TOKEN: "test:token",
          TG_WEBHOOK_SECRET: "test-secret",
          ADMIN_USER_IDS: "1",
          CALLBACK_HMAC_KEY: "test-hmac",
          PROCESSOR_FAKE_SECRET: "fake-secret",
          TEST_MIGRATIONS: migrations,
        },
      },
    }),
  ],
  test: {
    include: ["test/**/*.test.ts"],
    setupFiles: ["./test/setup.ts"],
  },
});
