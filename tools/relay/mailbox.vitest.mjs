import { env } from "cloudflare:workers";
import { runInDurableObject } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { NumbersMailbox } from "./worker.js";
import rawConfig from "./wrangler.test.jsonc?raw";

const SECRET = "s".repeat(64);
const MAILBOX_NAME = "numbers-mailbox-v1";
let mailboxSequence = 0;

afterEach(() => vi.restoreAllMocks());

function mailbox() {
  mailboxSequence += 1;
  return env.NUMBERS_MAILBOX.getByName(`test-mailbox-${mailboxSequence}`);
}

function relayRequest(requestEnv, endpoint, {
  method = "GET", publisher, body, urlSecret = SECRET,
} = {}) {
  const headers = new Headers();
  if (publisher !== undefined)
    headers.set("X-VibePulse-Publisher", publisher);
  const init = { method, headers };
  if (body !== undefined)
    init.body = typeof body === "string" ? body : JSON.stringify(body);
  const request = new Request(
      `https://relay.test/u/${urlSecret}${endpoint}`, init);
  return worker.fetch(request, requestEnv);
}

function fakeEnv({
  docs = [], publishResult = "stored", namespaceError = null,
  rpcError = null, includeBinding = true,
} = {}) {
  const calls = { names: [], publish: [], getDocs: [], kv: [] };
  const stub = {
    async publish(...args) {
      calls.publish.push(args);
      if (rpcError !== null) throw rpcError;
      return publishResult;
    },
    async getDocs(...args) {
      calls.getDocs.push(args);
      if (rpcError !== null) throw rpcError;
      return docs;
    },
  };
  const namespace = {
    getByName(name) {
      calls.names.push(name);
      if (namespaceError !== null) throw namespaceError;
      return stub;
    },
  };
  const VIBEPULSE = new Proxy({}, {
    get(_target, property) {
      calls.kv.push(String(property));
      throw new Error("KV request path operation must never occur");
    },
  });
  const requestEnv = { RELAY_SECRET: SECRET, VIBEPULSE };
  if (includeBinding) requestEnv.NUMBERS_MAILBOX = namespace;
  return { calls, requestEnv };
}

async function storedState(stub) {
  return runInDurableObject(stub, async (_instance, state) => ({
    publishers: state.storage.sql.exec(
      "SELECT publisher FROM publishers ORDER BY publisher",
    ).toArray().map((row) => row.publisher),
    documents: state.storage.sql.exec(`
      SELECT endpoint, publisher, received_at, body_json
      FROM documents ORDER BY endpoint, publisher
    `).toArray(),
  }));
}

describe("NumbersMailbox SQLite coordination", () => {
  it("registers eight simultaneous first publishers without losing peers",
     async () => {
    const stub = mailbox();
    const publishers = Array.from({ length: 8 }, (_, index) => `p${index}`);
    const results = await Promise.all(publishers.map((publisher, index) =>
      stub.publish(
        "/api/tokens", publisher,
        JSON.stringify({ publisher, value: index }),
      )));

    expect(results).toEqual(Array(8).fill("stored"));
    const state = await storedState(stub);
    expect(state.publishers).toEqual(publishers);
    expect(state.documents).toHaveLength(8);
  });

  it("strictly rejects a ninth publisher without displacing the first eight",
     async () => {
    const stub = mailbox();
    const firstEight = Array.from({ length: 8 }, (_, index) => `p${index}`);
    for (const publisher of firstEight) {
      await expect(stub.publish(
        "/api/tokens", publisher, JSON.stringify({ publisher }),
      )).resolves.toBe("stored");
    }

    await expect(stub.publish(
      "/api/tokens", "p8", JSON.stringify({ publisher: "p8" }),
    )).resolves.toBe("full");
    await expect(stub.publish(
      "/api/github", "p0", JSON.stringify({ stars: 99 }),
    )).resolves.toBe("stored");

    const state = await storedState(stub);
    expect(state.publishers).toEqual(firstEight);
    expect(state.documents.some((row) => row.publisher === "p8")).toBe(false);
    expect(state.documents).toContainEqual(expect.objectContaining({
      endpoint: "/api/github", publisher: "p0",
    }));
  });

  it("commits publisher registration and its endpoint document together",
     async () => {
    const stub = mailbox();
    await expect(stub.publish(
      "/api/tokens", "mac", JSON.stringify({ weekPct: 73 }),
    )).resolves.toBe("stored");

    const state = await storedState(stub);
    expect(state.publishers).toEqual(["mac"]);
    expect(state.documents).toEqual([expect.objectContaining({
      endpoint: "/api/tokens",
      publisher: "mac",
      received_at: 1,
      body_json: JSON.stringify({ weekPct: 73 }),
    })]);
  });

  it("rolls registration back when document storage fails", async () => {
    const stub = mailbox();
    await stub.getDocs("/api/tokens");
    await runInDurableObject(stub, async (_instance, state) => {
      state.storage.sql.exec(`
        CREATE TRIGGER fail_document_insert
        BEFORE INSERT ON documents
        BEGIN
          SELECT RAISE(ABORT, 'forced document failure');
        END
      `);
    });

    const failed = await runInDurableObject(stub, async (instance) => {
      try {
        await instance.publish(
          "/api/tokens", "mac", JSON.stringify({ weekPct: 73 }),
        );
        return false;
      } catch {
        return true;
      }
    });
    expect(failed).toBe(true);
    const state = await storedState(stub);
    expect(state.publishers).toEqual([]);
    expect(state.documents).toEqual([]);
    await runInDurableObject(stub, async (_instance, objectState) => {
      expect(objectState.storage.sql.exec(`
        SELECT receipt_sequence FROM mailbox_state WHERE singleton = 1
      `).one().receipt_sequence).toBe(0);
      objectState.storage.sql.exec("DROP TRIGGER fail_document_insert");
    });
    await expect(stub.publish(
      "/api/tokens", "pc", JSON.stringify({ weekPct: 74 }),
    )).resolves.toBe("stored");
    await expect(stub.getDocs("/api/tokens")).resolves.toEqual([{
      receivedAt: 1,
      publisher: "pc",
      body: { weekPct: 74 },
    }]);
  });

  it("skips a corrupt row without hiding a healthy publisher", async () => {
    const stub = mailbox();
    await stub.publish(
      "/api/github", "healthy", JSON.stringify({ stars: 99 }),
    );
    await runInDurableObject(stub, async (_instance, state) => {
      state.storage.sql.exec(
        "INSERT INTO publishers (publisher) VALUES (?)", "broken",
      );
      state.storage.sql.exec(`
        INSERT INTO documents (endpoint, publisher, received_at, body_json)
        VALUES (?, ?, ?, ?)
      `, "/api/github", "broken", 200, "not-json");
    });

    await expect(stub.getDocs("/api/github")).resolves.toEqual([{
      receivedAt: 1,
      publisher: "healthy",
      body: { stars: 99 },
    }]);
  });

  it("returns no documents when every stored row is corrupt", async () => {
    const stub = mailbox();
    await stub.getDocs("/api/github");
    await runInDurableObject(stub, async (_instance, state) => {
      state.storage.sql.exec(
        "INSERT INTO publishers (publisher) VALUES (?)", "broken",
      );
      state.storage.sql.exec(`
        INSERT INTO documents (endpoint, publisher, received_at, body_json)
        VALUES (?, ?, ?, ?)
      `, "/api/github", "broken", 200, "not-json");
    });

    await expect(stub.getDocs("/api/github")).resolves.toEqual([]);
  });

  it("owns receipt ordering even when direct RPC callers add timestamps",
     async () => {
    const stub = mailbox();
    await stub.publish(
      "/api/github", "mac", JSON.stringify({ source: "first" }),
      Number.MAX_SAFE_INTEGER,
    );
    await stub.publish(
      "/api/github", "pc", JSON.stringify({ source: "second" }), -1,
    );

    const docs = await stub.getDocs("/api/github");
    expect(docs.map((doc) => doc.receivedAt).sort()).toEqual([1, 2]);
    expect(docs.find((doc) => doc.publisher === "pc").body).toEqual({
      source: "second",
    });
  });

  it("keeps the later same-publisher body regardless of extra RPC input",
     async () => {
    const stub = mailbox();
    await stub.publish(
      "/api/max-tracker", "mac", JSON.stringify({ value: "old" }), 999999,
    );
    await stub.publish(
      "/api/max-tracker", "mac", JSON.stringify({ value: "new" }), 0,
    );

    await expect(stub.getDocs("/api/max-tracker")).resolves.toEqual([{
      receivedAt: 2,
      publisher: "mac",
      body: { value: "new" },
    }]);
  });
});

describe("public numbers Worker routing and wire contract", () => {
  for (const [endpoint, body] of [
    ["/api/tokens", { v: 2, weekPct: 73, weekObservedAt: 100 }],
    ["/api/max-tracker", { streak: 4, total: 12 }],
    ["/api/github", { stars: 99, issues: 3 }],
  ]) {
    it(`round-trips the first real publication for ${endpoint}`, async () => {
      const posted = await relayRequest(env, endpoint, {
        method: "POST", publisher: "mac", body,
      });
      expect(posted.status).toBe(200);
      expect(await posted.text()).toBe("ok");

      const fetched = await relayRequest(env, endpoint);
      expect(fetched.status).toBe(200);
      expect(await fetched.json()).toEqual(body);
      expect(fetched.headers.get("Content-Type")).toBe("application/json");
    });
  }

  it("routes every valid request to one deterministic mailbox without KV",
     async () => {
    const { calls, requestEnv } = fakeEnv({
      docs: [{ receivedAt: 100, publisher: "mac", body: { stars: 99 } }],
    });
    const posted = await relayRequest(requestEnv, "/api/tokens", {
      method: "POST", publisher: "mac", body: { weekPct: 73 },
    });
    const fetched = await relayRequest(requestEnv, "/api/github");

    expect(posted.status).toBe(200);
    expect(fetched.status).toBe(200);
    expect(calls.names).toEqual([MAILBOX_NAME, MAILBOX_NAME]);
    expect(calls.publish).toHaveLength(1);
    expect(calls.getDocs).toEqual([["/api/github"]]);
    expect(calls.kv).toEqual([]);
  });

  it("keeps 100 repeated GETs free of every KV request operation", async () => {
    const { calls, requestEnv } = fakeEnv({
      docs: [{ receivedAt: 100, publisher: "mac", body: { weekPct: 73 } }],
    });
    for (let index = 0; index < 100; index += 1) {
      const response = await relayRequest(requestEnv, "/api/tokens");
      expect(response.status).toBe(200);
    }
    expect(calls.names).toEqual(Array(100).fill(MAILBOX_NAME));
    expect(calls.kv).toEqual([]);
  });

  it("keeps wrong secrets and the activity endpoint hidden behind 404",
     async () => {
    const { calls, requestEnv } = fakeEnv();
    const wrongSecret = await relayRequest(requestEnv, "/api/tokens", {
      urlSecret: "x".repeat(64),
    });
    const activity = await relayRequest(requestEnv, "/api/agent-status");

    expect(wrongSecret.status).toBe(404);
    expect(activity.status).toBe(404);
    expect(calls.names).toEqual([]);
    expect(calls.kv).toEqual([]);
  });

  it("preserves missing-secret, method, body-size, and JSON responses",
     async () => {
    const configured = fakeEnv();
    const unconfigured = { ...configured.requestEnv, RELAY_SECRET: "short" };
    expect((await relayRequest(unconfigured, "/api/tokens")).status).toBe(503);
    expect(await (await relayRequest(
      configured.requestEnv, "/api/tokens", { method: "DELETE" },
    )).text()).toBe("method not allowed");
    expect((await relayRequest(configured.requestEnv, "/api/tokens", {
      method: "POST", publisher: "mac", body: "x".repeat(64 * 1024 + 1),
    })).status).toBe(413);
    expect((await relayRequest(configured.requestEnv, "/api/tokens", {
      method: "POST", publisher: "mac", body: "{not-json",
    })).status).toBe(400);
    expect(configured.calls.names).toEqual([]);
    expect(configured.calls.kv).toEqual([]);
  });

  it("sanitizes publishers before the mailbox RPC and preserves POST output",
     async () => {
    const { calls, requestEnv } = fakeEnv();
    const rawPublisher = `mac name/with?unsafe#chars-${"x".repeat(80)}`;
    const expected = rawPublisher.slice(0, 64)
      .replace(/[^A-Za-z0-9._-]/g, "_");
    const response = await relayRequest(requestEnv, "/api/tokens", {
      method: "POST", publisher: rawPublisher, body: { weekPct: 73 },
    });

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
    expect(calls.publish).toHaveLength(1);
    expect(calls.publish[0][0]).toBe("/api/tokens");
    expect(calls.publish[0][1]).toBe(expected);
    expect(JSON.parse(calls.publish[0][2])).toEqual({ weekPct: 73 });
    expect(calls.publish[0]).toHaveLength(3);
    expect(calls.kv).toEqual([]);
  });

  it("maps mailbox capacity to the existing strict 409 response", async () => {
    const { requestEnv } = fakeEnv({ publishResult: "full" });
    const response = await relayRequest(requestEnv, "/api/tokens", {
      method: "POST", publisher: "ninth", body: { weekPct: 73 },
    });
    expect(response.status).toBe(409);
    expect(await response.text()).toBe("too many publishers");
  });

  it("fails closed when the mailbox binding is missing or broken", async () => {
    const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
    const missing = fakeEnv({ includeBinding: false });
    const missingResponse = await relayRequest(
      missing.requestEnv, "/api/tokens",
    );
    expect(missingResponse.status).toBe(503);
    expect(await missingResponse.text()).toBe("relay unavailable");

    const broken = fakeEnv({ namespaceError: new Error("binding detail") });
    const brokenResponse = await relayRequest(
      broken.requestEnv, "/api/tokens",
    );
    expect(brokenResponse.status).toBe(503);
    const brokenBody = await brokenResponse.text();
    expect(brokenBody).toBe("relay unavailable");
    expect(brokenBody).not.toContain("binding detail");
    expect(diagnostic).toHaveBeenCalledTimes(2);
    for (const call of diagnostic.mock.calls)
      expect(JSON.parse(String(call[0]))).toEqual({
        level: "error",
        event: "numbers_mailbox_failure",
        operation: "read",
      });
  });

  it("turns storage RPC errors into a non-leaking non-success response",
     async () => {
    const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
    const sensitivePublisher = "private-mac";
    const sensitiveBody = "body-must-not-leak";
    const { requestEnv } = fakeEnv({
      rpcError: new Error(
        `${SECRET}:${sensitivePublisher}:${sensitiveBody}`,
      ),
    });
    const response = await relayRequest(requestEnv, "/api/tokens", {
      method: "POST", publisher: sensitivePublisher,
      body: { note: sensitiveBody, weekPct: 73 },
    });
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("relay unavailable");
    expect(diagnostic).toHaveBeenCalledTimes(1);
    const logged = String(diagnostic.mock.calls[0][0]);
    expect(JSON.parse(logged)).toEqual({
      level: "error",
      event: "numbers_mailbox_failure",
      operation: "publish",
    });
    expect(logged).not.toContain(SECRET);
    expect(logged).not.toContain(sensitivePublisher);
    expect(logged).not.toContain(sensitiveBody);
    diagnostic.mockRestore();
  });

  it("preserves per-pool token merging across real mailbox publishers",
     async () => {
    const stub = env.NUMBERS_MAILBOX.getByName(MAILBOX_NAME);
    await stub.publish("/api/tokens", "mac", JSON.stringify({
      v: 2,
      claudeWeekPct: 70, claudeWeekStale: true,
      claudeWeekObservedAt: 150,
      codexWeekPct: 41, codexWeekObservedAt: 190,
    }));
    await stub.publish("/api/tokens", "pc", JSON.stringify({
      v: 2,
      claudeWeekPct: 73, claudeWeekStale: false,
      claudeWeekObservedAt: 205,
      codexWeekPct: 39, codexWeekObservedAt: 100,
    }));

    const response = await relayRequest(env, "/api/tokens");
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      claudeWeekPct: 73,
      claudeWeekStale: false,
      claudeWeekObservedAt: 205,
      codexWeekPct: 41,
      codexWeekObservedAt: 190,
    });
    expect(response.headers.get("Content-Type")).toBe("application/json");
  });

  for (const endpoint of ["/api/max-tracker", "/api/github"]) {
    it(`preserves newest whole-document behavior for ${endpoint}`,
       async () => {
      const stub = mailbox();
      await stub.publish(
        endpoint, "mac", JSON.stringify({ source: "mac", value: 1 }),
      );
      await stub.publish(
        endpoint, "pc", JSON.stringify({ source: "pc", value: 2 }),
      );
      const requestEnv = {
        RELAY_SECRET: SECRET,
        NUMBERS_MAILBOX: { getByName: () => stub },
        VIBEPULSE: env.VIBEPULSE,
      };

      const response = await relayRequest(requestEnv, endpoint);
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ source: "pc", value: 2 });
      expect(response.headers.get("Content-Type")).toBe("application/json");
    });
  }

  it("preserves the existing JSON 404 for missing or corrupt rows", async () => {
    const stub = mailbox();
    await stub.getDocs("/api/github");
    await runInDurableObject(stub, async (_instance, state) => {
      state.storage.sql.exec(
        "INSERT INTO publishers (publisher) VALUES (?)", "broken",
      );
      state.storage.sql.exec(`
        INSERT INTO documents (endpoint, publisher, received_at, body_json)
        VALUES (?, ?, ?, ?)
      `, "/api/github", "broken", 200, "not-json");
    });
    const requestEnv = {
      RELAY_SECRET: SECRET,
      NUMBERS_MAILBOX: { getByName: () => stub },
      VIBEPULSE: env.VIBEPULSE,
    };

    const response = await relayRequest(requestEnv, "/api/github");
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "no data yet" });
    expect(response.headers.get("Content-Type")).toBe("application/json");
  });
});

describe("rollback-compatible KV bootstrap", () => {
  it("exports the mailbox class while preserving the old public KV contract",
     async () => {
    const bootstrap = await import("./bootstrap.js");
    expect(bootstrap.NumbersMailbox).toBe(NumbersMailbox);

    const publisher = "bootstrap-mac";
    const body = { stars: 99, issues: 3 };
    const url = `https://relay.test/u/${SECRET}/api/github`;
    const posted = await bootstrap.default.fetch(new Request(url, {
      method: "POST",
      headers: { "X-VibePulse-Publisher": publisher },
      body: JSON.stringify(body),
    }), env);
    expect(posted.status).toBe(200);
    expect(await posted.text()).toBe("ok");

    const stored = JSON.parse(
      await env.VIBEPULSE.get(`/api/github:${publisher}`),
    );
    expect(stored.publisher).toBe(publisher);
    expect(stored.body).toEqual(body);
    expect(stored.receivedAt).toEqual(expect.any(Number));

    const fetched = await bootstrap.default.fetch(new Request(url), env);
    expect(fetched.status).toBe(200);
    expect(await fetched.json()).toEqual(body);
    expect(fetched.headers.get("Content-Type")).toBe("application/json");
  });
});

describe("Wrangler Durable Object configuration", () => {
  it("retains KV only for rollback and declares one SQLite mailbox export", () => {
    const config = JSON.parse(rawConfig);
    expect(config.name).toBe("vibepulse-relay-bootstrap-test");
    expect(config.main).toBe("bootstrap.js");
    expect(config.compatibility_date).toBe("2026-08-22");
    expect(config.durable_objects).toEqual({
      bindings: [{
        name: "NUMBERS_MAILBOX",
        class_name: "NumbersMailbox",
      }],
    });
    expect(config.exports).toEqual({
      NumbersMailbox: { type: "durable-object", storage: "sqlite" },
    });
    expect(config.kv_namespaces).toEqual([expect.objectContaining({
      binding: "VIBEPULSE",
    })]);
    expect(config.secrets).toEqual({ required: ["RELAY_SECRET"] });
    expect(config).not.toHaveProperty("migrations");
  });
});
