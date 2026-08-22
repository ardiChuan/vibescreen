/*
 * Brevlådans sammanslagning, hållen stilla med node --test (ingen
 * Cloudflare behövs): färskast vinner PER POOL för /api/tokens, nyast
 * dokument för resten, och döda/korrupta dokument tystar aldrig de andra.
 *
 * Körs av test/run.sh när node finns; CI:s tokenserver-jobb kör den via
 * "node --test tools/relay/".
 */
import test from "node:test";
import assert from "node:assert/strict";
import worker, { mergeTokens, newestBody } from "./worker.js";

const SECRET = "s".repeat(64);
const PUBLISHER_INDEX_KEY = "__vibepulse_publishers_v1";

class MemoryKV {
  constructor() {
    this.values = new Map();
    this.getCalls = [];
    this.putCalls = [];
    this.listCalls = 0;
  }

  async get(key) {
    this.getCalls.push(key);
    return this.values.get(key) ?? null;
  }

  async put(key, value) {
    this.putCalls.push({ key, value });
    this.values.set(key, value);
  }

  async list() {
    this.listCalls += 1;
    throw new Error("KV.list must never be called");
  }
}

function relayRequest(kv, endpoint, {
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
  return worker.fetch(request, { RELAY_SECRET: SECRET, VIBEPULSE: kv });
}

function storeDoc(kv, endpoint, publisher, receivedAt, body) {
  kv.values.set(`${endpoint}:${publisher}`, JSON.stringify({
    receivedAt, publisher, body,
  }));
}

test("en ensam avsändare passerar orörd", () => {
  const doc = { receivedAt: 100, publisher: "mac",
                body: { v: 2, weekPct: 73, weekObservedAt: 90 } };
  assert.deepEqual(mergeTokens([doc]), doc.body);
});

test("varje pool tas från den maskin som såg den senast", () => {
  const mac = { receivedAt: 200, publisher: "mac", body: {
    v: 2,
    weekPct: 70, weekObservedAt: 150,        // äldre Claude-observation
    codexWeekPct: 41, codexWeekObservedAt: 190,  // färsk Codex (Macen kör Codex)
  } };
  const pc = { receivedAt: 210, publisher: "pc", body: {
    v: 2,
    weekPct: 73, weekObservedAt: 205,        // färsk Claude (PC:n frågade nyss)
    codexWeekPct: 39, codexWeekObservedAt: 100,  // gammal Codex
  } };
  const merged = mergeTokens([mac, pc]);
  assert.equal(merged.weekPct, 73, "Claude ska komma från PC:n");
  assert.equal(merged.codexWeekPct, 41, "Codex ska komma från Macen");
  assert.equal(merged.codexWeekObservedAt, 190,
               "stämpeln ska följa sin pools vinnare");
});

test("en pool bara den ena maskinen känner överlever", () => {
  const utan = { receivedAt: 300, publisher: "pc",
                 body: { v: 2, weekPct: 73, weekObservedAt: 295 } };
  const med = { receivedAt: 250, publisher: "mac",
                body: { v: 2, weekPct: 60, weekObservedAt: 200,
                        codexWeekPct: 41, codexWeekObservedAt: 240 } };
  const merged = mergeTokens([utan, med]);
  assert.equal(merged.codexWeekPct, 41,
               "att PC:n aldrig sett Codex får inte radera Codex-siffran");
  assert.equal(merged.weekPct, 73);
});

test("ostämplade fält följer det nyast mottagna dokumentet", () => {
  const gammal = { receivedAt: 100, publisher: "mac",
                   body: { v: 2, daySessions: 4 } };
  const ny = { receivedAt: 200, publisher: "pc",
               body: { v: 2, daySessions: 9 } };
  assert.equal(mergeTokens([gammal, ny]).daySessions, 9);
});

test("döda och korrupta dokument tystar inte de andra", () => {
  const frisk = { receivedAt: 100, publisher: "mac",
                  body: { v: 2, weekPct: 73 } };
  assert.equal(mergeTokens([null, { receivedAt: 1, body: null },
                            frisk]).weekPct, 73);
  assert.equal(mergeTokens([]), null);
  assert.equal(mergeTokens([null]), null);
});

test("newestBody är nyast mottagna, inget annat", () => {
  const a = { receivedAt: 100, publisher: "mac", body: { streak: 3 } };
  const b = { receivedAt: 200, publisher: "pc", body: { streak: 1 } };
  assert.equal(newestBody([a, b]).streak, 1);
  assert.equal(newestBody([]), null);
});

for (const [endpoint, body] of [
  ["/api/tokens", { v: 2, weekPct: 73, weekObservedAt: 100 }],
  ["/api/max-tracker", { streak: 4, total: 12 }],
  ["/api/github", { stars: 99, issues: 3 }],
]) {
  test(`första POST+GET fungerar utan KV.list för ${endpoint}`, async () => {
    const kv = new MemoryKV();
    const posted = await relayRequest(kv, endpoint, {
      method: "POST", publisher: "mac", body,
    });
    assert.equal(posted.status, 200);
    assert.deepEqual(JSON.parse(kv.values.get(PUBLISHER_INDEX_KEY)), ["mac"]);

    kv.getCalls = [];
    const fetched = await relayRequest(kv, endpoint);
    assert.equal(fetched.status, 200);
    assert.deepEqual(await fetched.json(), body);
    assert.deepEqual(kv.getCalls, [PUBLISHER_INDEX_KEY, `${endpoint}:mac`]);
    assert.equal(kv.listCalls, 0);
  });
}

test("100 upprepade token-GET använder aldrig KV.list", async () => {
  const kv = new MemoryKV();
  const body = { v: 2, weekPct: 73, weekObservedAt: 100 };
  const posted = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: "mac", body,
  });
  assert.equal(posted.status, 200);

  for (let i = 0; i < 100; i += 1) {
    const fetched = await relayRequest(kv, "/api/tokens");
    assert.equal(fetched.status, 200);
    assert.deepEqual(await fetched.json(), body);
  }
  assert.equal(kv.listCalls, 0);
});

test("en känd avsändare skriver bara om endpoint-dokumentet", async () => {
  const kv = new MemoryKV();
  kv.values.set(PUBLISHER_INDEX_KEY, JSON.stringify(["mac"]));
  storeDoc(kv, "/api/tokens", "mac", 100, { weekPct: 10 });

  const posted = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: "mac", body: { weekPct: 20 },
  });
  assert.equal(posted.status, 200);
  assert.deepEqual(kv.putCalls.map((call) => call.key), ["/api/tokens:mac"]);
  assert.deepEqual(JSON.parse(kv.values.get(PUBLISHER_INDEX_KEY)), ["mac"]);
});

test("den nionde avsändaren nekas utan att tränga undan de första åtta",
     async () => {
  const kv = new MemoryKV();
  const firstEight = Array.from({ length: 8 }, (_, i) => `publisher-${i + 1}`);
  for (const publisher of firstEight) {
    const response = await relayRequest(kv, "/api/tokens", {
      method: "POST", publisher, body: { publisher },
    });
    assert.equal(response.status, 200);
  }

  const ninth = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: "publisher-9", body: { publisher: 9 },
  });
  assert.equal(ninth.status, 409);
  assert.deepEqual(JSON.parse(kv.values.get(PUBLISHER_INDEX_KEY)), firstEight);
  assert.equal(kv.values.has("/api/tokens:publisher-9"), false);
  assert.equal(kv.listCalls, 0);
});

test("två avsändare behåller observationsmerge per tokenpool", async () => {
  const kv = new MemoryKV();
  kv.values.set(PUBLISHER_INDEX_KEY, JSON.stringify(["mac", "pc"]));
  storeDoc(kv, "/api/tokens", "mac", 200, {
    v: 2,
    weekPct: 70, weekObservedAt: 150,
    codexWeekPct: 41, codexWeekObservedAt: 190,
  });
  storeDoc(kv, "/api/tokens", "pc", 210, {
    v: 2,
    weekPct: 73, weekObservedAt: 205,
    codexWeekPct: 39, codexWeekObservedAt: 100,
  });

  const response = await relayRequest(kv, "/api/tokens");
  assert.equal(response.status, 200);
  const merged = await response.json();
  assert.equal(merged.weekPct, 73);
  assert.equal(merged.weekObservedAt, 205);
  assert.equal(merged.codexWeekPct, 41);
  assert.equal(merged.codexWeekObservedAt, 190);
  assert.equal(kv.listCalls, 0);
});

for (const endpoint of ["/api/max-tracker", "/api/github"]) {
  test(`nyaste hela dokumentet vinner fortfarande för ${endpoint}`,
       async () => {
    const kv = new MemoryKV();
    kv.values.set(PUBLISHER_INDEX_KEY, JSON.stringify(["mac", "pc"]));
    storeDoc(kv, endpoint, "mac", 100, { source: "mac", value: 1 });
    storeDoc(kv, endpoint, "pc", 200, { source: "pc", value: 2 });

    const response = await relayRequest(kv, endpoint);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { source: "pc", value: 2 });
    assert.equal(kv.listCalls, 0);
  });
}

for (const [name, rawIndex] of [
  ["trasig JSON", "{"],
  ["inte en array", JSON.stringify({ publisher: "mac" })],
  ["dubblett", JSON.stringify(["mac", "mac"])],
  ["för många", JSON.stringify(Array.from({ length: 9 }, (_, i) => `p${i}`))],
  ["ogiltigt namn", JSON.stringify(["bad name"])],
]) {
  test(`ogiltigt publisher-index (${name}) ger säkert befintligt 404`,
       async () => {
    const kv = new MemoryKV();
    kv.values.set(PUBLISHER_INDEX_KEY, rawIndex);
    storeDoc(kv, "/api/tokens", "mac", 100, { weekPct: 73 });

    const response = await relayRequest(kv, "/api/tokens");
    assert.equal(response.status, 404);
    assert.deepEqual(await response.json(), { error: "no data yet" });
    assert.equal(response.headers.get("Content-Type"), "application/json");
    assert.equal(kv.listCalls, 0);
  });
}

test("ett korrupt avsändardokument tystar inte ett friskt", async () => {
  const kv = new MemoryKV();
  kv.values.set(PUBLISHER_INDEX_KEY, JSON.stringify(["broken", "healthy"]));
  kv.values.set("/api/github:broken", "not json");
  storeDoc(kv, "/api/github", "healthy", 100, { stars: 99 });

  const response = await relayRequest(kv, "/api/github");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { stars: 99 });
  assert.equal(kv.listCalls, 0);
});

test("bara korrupt avsändar-JSON ger säkert befintligt 404", async () => {
  const kv = new MemoryKV();
  kv.values.set(PUBLISHER_INDEX_KEY, JSON.stringify(["broken"]));
  kv.values.set("/api/github:broken", "not json");

  const response = await relayRequest(kv, "/api/github");
  assert.equal(response.status, 404);
  assert.deepEqual(await response.json(), { error: "no data yet" });
  assert.equal(response.headers.get("Content-Type"), "application/json");
  assert.equal(kv.listCalls, 0);
});

test("fel hemlighet och agent-status förblir 404", async () => {
  const kv = new MemoryKV();
  const wrongSecret = await relayRequest(kv, "/api/tokens", {
    urlSecret: "x".repeat(64),
  });
  assert.equal(wrongSecret.status, 404);

  const agentStatus = await relayRequest(kv, "/api/agent-status");
  assert.equal(agentStatus.status, 404);
  assert.deepEqual(kv.getCalls, []);
  assert.equal(kv.listCalls, 0);
});

test("en kropp över 64 KiB nekas med 413 före JSON-tolkning", async () => {
  const kv = new MemoryKV();
  const response = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: "mac", body: "x".repeat(64 * 1024 + 1),
  });
  assert.equal(response.status, 413);
  assert.equal(kv.putCalls.length, 0);
  assert.equal(kv.listCalls, 0);
});

test("felaktig JSON nekas med 400 utan KV-skrivning", async () => {
  const kv = new MemoryKV();
  const response = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: "mac", body: "{not-json",
  });
  assert.equal(response.status, 400);
  assert.equal(kv.putCalls.length, 0);
  assert.equal(kv.listCalls, 0);
});

test("avsändarnamn saneras och begränsas till 64 tecken", async () => {
  const kv = new MemoryKV();
  const rawPublisher = `mac name/with?unsafe#chars-${"x".repeat(80)}`;
  const expected = rawPublisher.slice(0, 64).replace(/[^A-Za-z0-9._-]/g, "_");
  const response = await relayRequest(kv, "/api/tokens", {
    method: "POST", publisher: rawPublisher, body: { weekPct: 73 },
  });
  assert.equal(response.status, 200);
  assert.match(expected, /^[A-Za-z0-9._-]{1,64}$/);
  assert.deepEqual(JSON.parse(kv.values.get(PUBLISHER_INDEX_KEY)), [expected]);
  assert.equal(kv.values.has(`/api/tokens:${expected}`), true);
  const stored = JSON.parse(kv.values.get(`/api/tokens:${expected}`));
  assert.equal(stored.publisher, expected);
  assert.equal(kv.listCalls, 0);
});
