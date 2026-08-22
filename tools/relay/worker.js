/*
 * VibePulse-brevlådan: en Cloudflare Worker + KV som håller tjänstens
 * senaste siffror så panelen kan hämta dem från vilket nät som helst.
 *
 * Rollen är medvetet dum: den kan ingenting, vet ingenting och har inga
 * nycklar. Tjänsten (tools/tokenserver --publish) POSTar färdiga JSON-
 * kroppar hit; panelen GETtar dem när LAN:et inte svarar. Det som ligger
 * här är SIFFROR — kvot, burn rate, Max Tracker, GitHub. Agentstatus och
 * Needs You publiceras aldrig (firmwarens test/test_relay_boundary.py och
 * tjänstens publisher.py håller den gränsen från var sitt håll).
 *
 * Åtkomstkontrollen ÄR sökvägen: /u/<hemlighet>/api/... där hemligheten
 * är minst 32 slumpade byte ur secrets.h (TK_VIBEPULSE_RELAY_URL). Samma
 * skyddsnivå som en privat delningslänk — rätt nivå för procentsiffror,
 * och skälet till att inget känsligare än siffror får bo här.
 *
 * Flera avsändare (en Mac som sover, en alltid-på-PC) publicerar till
 * samma brevlåda under eget namn. Läsningen slår ihop dem:
 *
 *   /api/tokens      — färskast VINNER PER POOL: varje kvotpool bär redan
 *                      sin egen observationsstämpel (weekObservedAt,
 *                      modelObservedAt, ... — byggda för stalenesslogiken),
 *                      så Codex-siffran kan komma från Macen som körde
 *                      Codex senast medan Claude-siffran kommer från PC:n
 *                      som frågade Anthropic för tio sekunder sedan.
 *   /api/max-tracker — nyast mottagna dokument vinner helt. Historiken är
 *                      per maskin; en dag-för-dag-sammanslagning vore att
 *                      hitta på data ingen maskin har sett. Ärlig gräns:
 *                      kör du Max Tracker-historik från två maskiner är
 *                      det den senast publicerande som syns.
 *   /api/github      — nyast vinner. Båda frågar samma publika API.
 *
 * Deploy: se README.md i den här katalogen. KV-bindningen heter VIBEPULSE.
 */

const ENDPOINTS = ["/api/tokens", "/api/max-tracker", "/api/github"];
const MAX_BODY_BYTES = 64 * 1024; // largest honest payload is ~8 kB
const MAX_PUBLISHERS = 8;
const PUBLISHER_INDEX_KEY = "__vibepulse_publishers_v1";
const PUBLISHER_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;

/*
 * Sammanslagningen för /api/tokens, som ren funktion så testerna kan hålla
 * den stilla (node --test i test.mjs — ingen Cloudflare behövs).
 *
 * Regeln: basen är det nyast MOTTAGNA dokumentet (fält utan stämpel följer
 * det). Sedan får varje observationsstämplad fältgrupp — prefixet framför
 * "ObservedAt", t.ex. week/model/codexWeek — sina fält från det dokument
 * vars stämpel för JUST den gruppen är färskast. En grupp ett dokument
 * saknar lämnas orörd: att en maskin aldrig sett Codex betyder inte att
 * Codex-siffran ska försvinna.
 */
export function mergeTokens(docs) {
  const alive = docs.filter((d) => d && typeof d.body === "object" &&
                                   d.body !== null);
  if (alive.length === 0) return null;
  alive.sort((a, b) => (b.receivedAt || 0) - (a.receivedAt || 0));
  const merged = { ...alive[0].body };

  const groups = new Set();
  for (const doc of alive)
    for (const key of Object.keys(doc.body))
      if (key.endsWith("ObservedAt")) groups.add(key.slice(0, -10));

  for (const group of groups) {
    const stamp = group + "ObservedAt";
    let winner = null;
    for (const doc of alive) {
      const at = doc.body[stamp];
      if (typeof at !== "number") continue;
      if (winner === null || at > winner.body[stamp]) winner = doc;
    }
    if (winner === null) continue;
    for (const key of Object.keys(winner.body))
      if (key === stamp || (key.startsWith(group) &&
                            !key.endsWith("ObservedAt")))
        merged[key] = winner.body[key];
  }
  return merged;
}

/* Nyast mottagna dokument, för endpoints utan sammanslagning. */
export function newestBody(docs) {
  const alive = docs.filter((d) => d && typeof d.body === "object" &&
                                   d.body !== null);
  if (alive.length === 0) return null;
  alive.sort((a, b) => (b.receivedAt || 0) - (a.receivedAt || 0));
  return alive[0].body;
}

function parsePath(url, secret) {
  const prefix = `/u/${secret}`;
  const path = new URL(url).pathname;
  if (!path.startsWith(prefix + "/")) return null;
  const endpoint = path.slice(prefix.length);
  return ENDPOINTS.includes(endpoint) ? endpoint : null;
}

function parsePublisherIndex(raw) {
  if (!raw) return [];
  try {
    const publishers = JSON.parse(raw);
    if (!Array.isArray(publishers) || publishers.length > MAX_PUBLISHERS)
      return [];
    const unique = new Set();
    for (const publisher of publishers) {
      if (typeof publisher !== "string" ||
          !PUBLISHER_PATTERN.test(publisher) || unique.has(publisher))
        return [];
      unique.add(publisher);
    }
    return publishers;
  } catch {
    return [];
  }
}

async function ensurePublisher(env, publisher) {
  const publishers = parsePublisherIndex(
      await env.VIBEPULSE.get(PUBLISHER_INDEX_KEY));
  if (publishers.includes(publisher)) return true;
  if (publishers.length >= MAX_PUBLISHERS) return false;
  await env.VIBEPULSE.put(PUBLISHER_INDEX_KEY,
                          JSON.stringify([...publishers, publisher]));
  return true;
}

async function readDocs(env, endpoint) {
  const publishers = parsePublisherIndex(
      await env.VIBEPULSE.get(PUBLISHER_INDEX_KEY));
  const docs = [];
  for (const publisher of publishers) {
    const raw = await env.VIBEPULSE.get(`${endpoint}:${publisher}`);
    if (!raw) continue;
    try {
      docs.push(JSON.parse(raw));
    } catch {
      /* ett korrupt dokument tystar inte de andra */
    }
  }
  return docs;
}

export default {
  async fetch(request, env) {
    // Hemligheten är en Worker-secret (wrangler secret put RELAY_SECRET),
    // aldrig kod. Utan den svarar brevlådan ingenting alls.
    const secret = env.RELAY_SECRET;
    if (!secret || secret.length < 32)
      return new Response("relay not configured", { status: 503 });

    const endpoint = parsePath(request.url, secret);
    if (endpoint === null) return new Response("not found", { status: 404 });

    if (request.method === "POST" || request.method === "PUT") {
      const publisher =
          (request.headers.get("X-VibePulse-Publisher") || "unnamed")
              .slice(0, 64).replace(/[^A-Za-z0-9._-]/g, "_");
      const raw = await request.text();
      if (raw.length > MAX_BODY_BYTES)
        return new Response("too large", { status: 413 });
      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return new Response("not json", { status: 400 });
      }
      if (!await ensurePublisher(env, publisher))
        return new Response("too many publishers", { status: 409 });
      const doc = JSON.stringify({ receivedAt: Date.now() / 1000,
                                   publisher, body });
      await env.VIBEPULSE.put(`${endpoint}:${publisher}`, doc);
      return new Response("ok", { status: 200 });
    }

    if (request.method === "GET") {
      const docs = await readDocs(env, endpoint);
      const merged = endpoint === "/api/tokens" ? mergeTokens(docs)
                                                : newestBody(docs);
      if (merged === null)
        return new Response(JSON.stringify({ error: "no data yet" }),
                            { status: 404,
                              headers: { "Content-Type": "application/json" } });
      return new Response(JSON.stringify(merged),
                          { headers: { "Content-Type": "application/json" } });
    }

    return new Response("method not allowed", { status: 405 });
  },
};
