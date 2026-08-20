export { InteractionMailbox } from "./mailbox";

import {
  isBearerToken,
  isMailboxId,
  isRequestId,
  readEnvelope,
  REQUEST_CIPHERTEXT_BYTES,
  sha256Hex,
  VERDICT_CIPHERTEXT_BYTES,
} from "./envelope";

type Route =
  | { kind: "request_item"; mailbox: string; requestId: string }
  | { kind: "next_request"; mailbox: string }
  | { kind: "put_verdict"; mailbox: string; requestId: string }
  | { kind: "list_verdicts"; mailbox: string };

type LogRoute =
  | "put_request"
  | "delete_request"
  | "next_request"
  | "put_verdict"
  | "list_verdicts"
  | "unknown";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const startedAt = Date.now();
    let logRoute: LogRoute = "unknown";
    let response: Response;
    try {
      const url = new URL(request.url);
      const route = url.search === "" ? matchRoute(url.pathname) : null;
      if (route === null || route.mailbox !== env.MAILBOX_ID ||
          !isMailboxId(env.MAILBOX_ID)) {
        response = textResponse("Not found", 404);
      } else {
        const dispatched = await dispatch(request, env, route);
        logRoute = dispatched.route;
        response = dispatched.response;
      }
    } catch {
      response = textResponse("Internal error", 500);
    }
    console.log(JSON.stringify({
      event: "interaction_relay_request",
      route: logRoute,
      status: response.status,
      durationMs: Math.max(0, Date.now() - startedAt),
    }));
    return response;
  },
} satisfies ExportedHandler<Env>;

async function dispatch(
  request: Request,
  env: Env,
  route: Route,
): Promise<{ route: LogRoute; response: Response }> {
  switch (route.kind) {
    case "request_item":
      if (request.method === "PUT") {
        return {
          route: "put_request",
          response: await putRequest(request, env, route.requestId),
        };
      }
      if (request.method === "DELETE") {
        return {
          route: "delete_request",
          response: await deleteRequest(request, env, route.requestId),
        };
      }
      return { route: "unknown", response: methodNotAllowed("PUT, DELETE") };
    case "next_request":
      return request.method === "GET"
        ? { route: "next_request", response: await nextRequest(request, env) }
        : { route: "unknown", response: methodNotAllowed("GET") };
    case "put_verdict":
      return request.method === "POST"
        ? {
            route: "put_verdict",
            response: await putVerdict(request, env, route.requestId),
          }
        : { route: "unknown", response: methodNotAllowed("POST") };
    case "list_verdicts":
      return request.method === "GET"
        ? { route: "list_verdicts", response: await listVerdicts(request, env) }
        : { route: "unknown", response: methodNotAllowed("GET") };
  }
}

async function putRequest(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  if (!await authorized(request, env.MAC_TOKEN)) {
    return textResponse("Not found", 404);
  }
  const parsed = await readEnvelope(request, REQUEST_CIPHERTEXT_BYTES);
  if (!parsed.ok) {
    return textResponse(statusText(parsed.status), parsed.status);
  }
  const hash = await sha256Hex(parsed.text);
  const mailbox = env.INTERACTION_MAILBOX.getByName(env.MAILBOX_ID);
  const result = await mailbox.putRequest(
    requestId,
    parsed.text,
    hash,
    Date.now(),
  );
  switch (result) {
    case "created":
      return emptyResponse(201);
    case "existing":
      return emptyResponse(200);
    case "conflict":
      return textResponse("Conflict", 409);
    case "full":
      return textResponse("Mailbox full", 429);
  }
}

async function nextRequest(request: Request, env: Env): Promise<Response> {
  if (!await authorized(request, env.PANEL_TOKEN)) {
    return textResponse("Not found", 404);
  }
  const mailbox = env.INTERACTION_MAILBOX.getByName(env.MAILBOX_ID);
  const pending = await mailbox.nextRequest(Date.now());
  if (pending === null) {
    return emptyResponse(204);
  }
  return jsonResponse({
    envelope: JSON.parse(pending.envelope) as unknown,
    expiresAtMs: pending.expiresAtMs,
    requestId: pending.requestId,
  });
}

async function putVerdict(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  if (!await authorized(request, env.PANEL_TOKEN)) {
    return textResponse("Not found", 404);
  }
  const parsed = await readEnvelope(request, VERDICT_CIPHERTEXT_BYTES);
  if (!parsed.ok) {
    return textResponse(statusText(parsed.status), parsed.status);
  }
  const hash = await sha256Hex(parsed.text);
  const mailbox = env.INTERACTION_MAILBOX.getByName(env.MAILBOX_ID);
  const result = await mailbox.putVerdict(
    requestId,
    parsed.text,
    hash,
    Date.now(),
  );
  switch (result) {
    case "created":
      return emptyResponse(201);
    case "existing":
      return emptyResponse(200);
    case "conflict":
      return textResponse("Conflict", 409);
    case "missing":
      return textResponse("Not found", 404);
  }
}

async function listVerdicts(request: Request, env: Env): Promise<Response> {
  if (!await authorized(request, env.MAC_TOKEN)) {
    return textResponse("Not found", 404);
  }
  const mailbox = env.INTERACTION_MAILBOX.getByName(env.MAILBOX_ID);
  const verdicts = await mailbox.listVerdicts(Date.now());
  if (verdicts.length === 0) {
    return emptyResponse(204);
  }
  return jsonResponse({
    // One fixed-size verdict plus its small wrapper stays below the host's
    // 4096-byte response cap. Remaining rows retain their stable order and
    // surface on the next poll after this request is deleted.
    verdicts: verdicts.slice(0, 1).map((verdict) => ({
      envelope: JSON.parse(verdict.envelope) as unknown,
      requestId: verdict.requestId,
      verdictAtMs: verdict.verdictAtMs,
    })),
  });
}

async function deleteRequest(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  if (!await authorized(request, env.MAC_TOKEN)) {
    return textResponse("Not found", 404);
  }
  const mailbox = env.INTERACTION_MAILBOX.getByName(env.MAILBOX_ID);
  await mailbox.deleteRequest(requestId, Date.now());
  return emptyResponse(204);
}

function matchRoute(pathname: string): Route | null {
  let match = /^\/v1\/mailboxes\/(vp_[A-Za-z0-9_-]{16})\/requests\/([A-Za-z0-9_-]{22})$/.exec(pathname);
  if (match !== null && isRequestId(match[2])) {
    return { kind: "request_item", mailbox: match[1], requestId: match[2] };
  }
  match = /^\/v1\/mailboxes\/(vp_[A-Za-z0-9_-]{16})\/requests\/next$/.exec(pathname);
  if (match !== null) {
    return { kind: "next_request", mailbox: match[1] };
  }
  match = /^\/v1\/mailboxes\/(vp_[A-Za-z0-9_-]{16})\/requests\/([A-Za-z0-9_-]{22})\/verdict$/.exec(pathname);
  if (match !== null && isRequestId(match[2])) {
    return { kind: "put_verdict", mailbox: match[1], requestId: match[2] };
  }
  match = /^\/v1\/mailboxes\/(vp_[A-Za-z0-9_-]{16})\/verdicts$/.exec(pathname);
  return match === null
    ? null
    : { kind: "list_verdicts", mailbox: match[1] };
}

async function authorized(request: Request, expected: string): Promise<boolean> {
  const authorization = request.headers.get("Authorization");
  const match = authorization === null
    ? null
    : /^Bearer ([A-Za-z0-9_-]{43})$/.exec(authorization);
  const supplied = match?.[1] ?? "";
  const encoder = new TextEncoder();
  const [suppliedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  return match !== null && isBearerToken(supplied) &&
    isBearerToken(expected) && crypto.subtle.timingSafeEqual(
      new Uint8Array(suppliedHash),
      new Uint8Array(expectedHash),
    );
}

function statusText(status: 400 | 413 | 415): string {
  switch (status) {
    case 400:
      return "Bad request";
    case 413:
      return "Payload too large";
    case 415:
      return "Unsupported media type";
  }
}

function hardenedHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set("Cache-Control", "no-store");
  return headers;
}

function emptyResponse(status: number): Response {
  return new Response(null, { status, headers: hardenedHeaders() });
}

function textResponse(
  body: string,
  status: number,
  extraHeaders?: HeadersInit,
): Response {
  return new Response(body, {
    status,
    headers: hardenedHeaders({
      "Content-Type": "text/plain; charset=utf-8",
      ...Object.fromEntries(new Headers(extraHeaders)),
    }),
  });
}

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: hardenedHeaders({ "Content-Type": "application/json" }),
  });
}

function methodNotAllowed(allow: string): Response {
  return textResponse("Method not allowed", 405, { Allow: allow });
}
