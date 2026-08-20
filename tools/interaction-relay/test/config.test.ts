import { describe, expect, it } from "vitest";
import raw from "../wrangler.jsonc?raw";


describe("interaction relay Worker configuration", () => {
  it("pins one typed SQLite Durable Object without secrets", () => {
    const config = JSON.parse(raw) as Record<string, unknown>;

    expect(config.name).toBe("vibepulse-interaction-relay");
    expect(config.main).toBe("src/index.ts");
    expect(config.compatibility_date).toBe("2026-08-20");
    expect(config.compatibility_flags).toContain("nodejs_compat");
    expect(config.observability).toMatchObject({ enabled: true });
    expect(config.durable_objects).toEqual({
      bindings: [{
        name: "INTERACTION_MAILBOX",
        class_name: "InteractionMailbox",
      }],
    });
    expect(config.exports).toEqual({
      InteractionMailbox: { type: "durable-object", storage: "sqlite" },
    });
    expect(config).not.toHaveProperty("migrations");
    expect(config).not.toHaveProperty("kv_namespaces");
    expect(raw).not.toContain("MAC_TOKEN");
    expect(raw).not.toContain("PANEL_TOKEN");
  });
});
