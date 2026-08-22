import { env } from "cloudflare:workers";
import { runInDurableObject } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import worker from "./worker.js";
import rawConfig from "./wrangler.jsonc?raw";

const SECRET = "s".repeat(64);
const MAILBOX_NAME = "numbers-mailbox-v1";
let mailboxSequence = 0;

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
        JSON.stringify({ publisher, value: index }), 100 + index,
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
    for (const [index, publisher] of firstEight.entries()) {
      await expect(stub.publish(
        "/api/tokens", publisher, JSON.stringify({ publisher }), 100 + index,
      )).resolves.toBe("stored");
    }

    await expect(stub.publish(
      "/api/tokens", "p8", JSON.stringify({ publisher: "p8" }), 200,
    )).resolves.toBe("full");
    await expect(stub.publish(
      "/api/github", "p0", JSON.stringify({ stars: 99 }), 201,
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
      "/api/tokens", "mac", JSON.stringify({ weekPct: 73 }), 100,
    )).resolves.toBe("stored");

    const state = await storedState(stub);
    expect(state.publishers).toEqual(["mac"]);
    expect(state.documents).toEqual([expect.objectContaining({
      endpoint: "/api/tokens",
      publisher: "mac",
      received_at: 100,
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

    await expect(stub.publish(
      "/api/tokens", "mac", JSON.stringify({ weekPct: 73 }), 100,
    )).rejects.toThrow();
    const state = await storedState(stub);
    expect(state.publishers).toEqual([]);
    expect(state.documents).toEqual([]);
  });

  it("skips a corrupt row without hiding a healthy publisher", async () => {
    const stub = mailbox();
    await stub.publish(
      "/api/github", "healthy", JSON.stringify({ stars: 99 }), 100,
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
      receivedAt: 100,
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
});

describe("public numbers Worker routing and wire contract", () => {
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
    expect(await brokenResponse.text()).toBe("relay unavailable");
    expect(await brokenResponse.text()).not.toContain("binding detail");
  });

  it("turns storage RPC errors into a non-leaking non-success response",
     async () => {
    const { requestEnv } = fakeEnv({
      rpcError: new Error("forced document failure"),
    });
    const response = await relayRequest(requestEnv, "/api/tokens", {
      method: "POST", publisher: "mac", body: { weekPct: 73 },
    });
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("relay unavailable");
  });

  it("preserves per-pool token merging across real mailbox publishers",
     async () => {
    const stub = env.NUMBERS_MAILBOX.getByName(MAILBOX_NAME);
    await stub.publish("/api/tokens", "mac", JSON.stringify({
      v: 2,
      weekPct: 70, weekObservedAt: 150,
      codexWeekPct: 41, codexWeekObservedAt: 190,
    }), 200);
    await stub.publish("/api/tokens", "pc", JSON.stringify({
      v: 2,
      weekPct: 73, weekObservedAt: 205,
      codexWeekPct: 39, codexWeekObservedAt: 100,
    }), 210);

    const response = await relayRequest(env, "/api/tokens");
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      weekPct: 73,
      weekObservedAt: 205,
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
        endpoint, "mac", JSON.stringify({ source: "mac", value: 1 }), 100,
      );
      await stub.publish(
        endpoint, "pc", JSON.stringify({ source: "pc", value: 2 }), 200,
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

describe("Wrangler Durable Object configuration", () => {
  it("retains KV only for rollback and declares one SQLite mailbox export", () => {
    const config = JSON.parse(rawConfig);
    expect(config.main).toBe("worker.js");
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
    expect(config).not.toHaveProperty("migrations");
  });
});
