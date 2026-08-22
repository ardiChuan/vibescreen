/*
 * Rollback-compatible first stage for introducing NumbersMailbox.
 *
 * This entrypoint deliberately keeps the original KV request path while it
 * exports the new Durable Object class. Deploy it first to apply the class
 * lifecycle change without changing public behavior; later deployments can
 * switch main to worker.js and can roll back only as far as this bootstrap.
 */

import { mergeTokens, newestBody } from "./merge.js";

export { NumbersMailbox } from "./worker.js";

const ENDPOINTS = ["/api/tokens", "/api/max-tracker", "/api/github"];
const MAX_BODY_BYTES = 64 * 1024;
const MAX_PUBLISHERS = 8;

function parsePath(url, secret) {
  const prefix = `/u/${secret}`;
  const path = new URL(url).pathname;
  if (!path.startsWith(prefix + "/")) return null;
  const endpoint = path.slice(prefix.length);
  return ENDPOINTS.includes(endpoint) ? endpoint : null;
}

async function readDocs(env, endpoint) {
  const listed = await env.VIBEPULSE.list({ prefix: `${endpoint}:` });
  const docs = [];
  for (const key of listed.keys.slice(0, MAX_PUBLISHERS)) {
    const raw = await env.VIBEPULSE.get(key.name);
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
      const doc = JSON.stringify({
        receivedAt: Date.now() / 1000,
        publisher,
        body,
      });
      await env.VIBEPULSE.put(`${endpoint}:${publisher}`, doc);
      return new Response("ok", { status: 200 });
    }

    if (request.method === "GET") {
      const docs = await readDocs(env, endpoint);
      const merged = endpoint === "/api/tokens" ? mergeTokens(docs)
                                                : newestBody(docs);
      if (merged === null)
        return new Response(JSON.stringify({ error: "no data yet" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      return new Response(JSON.stringify(merged), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("method not allowed", { status: 405 });
  },
};
