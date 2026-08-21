import { SELF, reset } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";

const MAILBOX = "vp_A1b2C3d4E5f6G7h8";
const OTHER_MAILBOX = "vp_Z9y8X7w6V5u4T3s2";
const MAC_TOKEN = "ERERERERERERERERERERERERERERERERERERERERERE";
const PANEL_TOKEN = "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI";
const REQUEST_CIPHERTEXT_BYTES = 2048 + 16;
const VERDICT_CIPHERTEXT_BYTES = 1024 + 16;
const STATUS_CIPHERTEXT_BYTES = 2816 + 16;

afterEach(async () => {
  vi.restoreAllMocks();
  await reset();
});

function b64url(size: number, fill = 0x5a): string {
  const bytes = new Uint8Array(size).fill(fill);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_")
    .replace(/=+$/, "");
}

function requestId(index = 1): string {
  const bytes = new Uint8Array(16);
  bytes[15] = index;
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_")
    .replace(/=+$/, "");
}

function envelope(ciphertextBytes: number, fill = 0x5a): string {
  return JSON.stringify({
    ciphertext: b64url(ciphertextBytes, fill),
    nonce: b64url(12, fill ^ 0xff),
    v: 1,
  });
}

function auth(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

function requestPath(id = requestId()): string {
  return `/v1/mailboxes/${MAILBOX}/requests/${id}`;
}

function verdictPath(id = requestId()): string {
  return `${requestPath(id)}/verdict`;
}

function statusPath(): string {
  return `/v1/mailboxes/${MAILBOX}/status`;
}

async function fetchPath(path: string, init?: RequestInit): Promise<Response> {
  return SELF.fetch(`https://relay.invalid${path}`, init);
}

function expectHardened(response: Response): void {
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(response.headers.get("Access-Control-Allow-Origin")).toBeNull();
}

function jsonRequest(
  method: string,
  body: BodyInit,
  token: string,
  headers: Record<string, string> = {},
): RequestInit {
  return {
    method,
    body,
    headers: {
      ...auth(token),
      "Content-Type": "application/json",
      ...headers,
    },
  };
}

describe("encrypted interaction relay HTTP API", () => {
  it("publishes and replaces one opaque status envelope", async () => {
    const first = envelope(STATUS_CIPHERTEXT_BYTES, 0x41);
    const second = envelope(STATUS_CIPHERTEXT_BYTES, 0x42);

    let response = await fetchPath(
      statusPath(), jsonRequest("PUT", first, MAC_TOKEN));
    expect(response.status).toBe(201);
    expectHardened(response);

    response = await fetchPath(statusPath(), { headers: auth(PANEL_TOKEN) });
    expect(response.status).toBe(200);
    expectHardened(response);
    expect(response.headers.get("Content-Type")).toBe("application/json");
    expect(await response.json()).toEqual({
      envelope: JSON.parse(first),
      expiresAtMs: expect.any(Number),
      storedAtMs: expect.any(Number),
    });

    response = await fetchPath(
      statusPath(), jsonRequest("PUT", second, MAC_TOKEN));
    expect(response.status).toBe(201);
    response = await fetchPath(statusPath(), { headers: auth(PANEL_TOKEN) });
    expect((await response.json() as { envelope: unknown }).envelope)
      .toEqual(JSON.parse(second));
  });

  it("keeps status roles, methods, media type, and frame size strict", async () => {
    const valid = envelope(STATUS_CIPHERTEXT_BYTES);
    const unauthorized: Array<[RequestInit, string]> = [
      [jsonRequest("PUT", valid, PANEL_TOKEN), "panel put"],
      [{ headers: auth(MAC_TOKEN) }, "Mac get"],
      [jsonRequest("PUT", valid, "wrong"), "wrong token"],
    ];
    for (const [init, name] of unauthorized) {
      const response = await fetchPath(statusPath(), init);
      expect(response.status, name).toBe(404);
      expectHardened(response);
    }

    for (const [method, token] of [["POST", MAC_TOKEN], ["DELETE", PANEL_TOKEN]]) {
      const response = await fetchPath(statusPath(), {
        method,
        headers: auth(token),
      });
      expect(response.status, method).toBe(405);
      expectHardened(response);
    }

    let response = await fetchPath(statusPath(), {
      method: "PUT",
      body: valid,
      headers: auth(MAC_TOKEN),
    });
    expect(response.status).toBe(415);
    for (const size of [
      REQUEST_CIPHERTEXT_BYTES,
      STATUS_CIPHERTEXT_BYTES - 1,
      STATUS_CIPHERTEXT_BYTES + 1,
    ]) {
      response = await fetchPath(
        statusPath(),
        jsonRequest("PUT", envelope(size), MAC_TOKEN),
      );
      expect(response.status, String(size)).toBe(400);
      expectHardened(response);
    }
  });

  it("returns an empty hardened response before status exists", async () => {
    const response = await fetchPath(
      statusPath(), { headers: auth(PANEL_TOKEN) });
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
    expectHardened(response);
  });

  it("supports the complete opaque request and verdict lifecycle", async () => {
    const id = requestId();
    const requestEnvelope = envelope(REQUEST_CIPHERTEXT_BYTES);
    const verdictEnvelope = envelope(VERDICT_CIPHERTEXT_BYTES, 0x33);

    let response = await fetchPath(
      requestPath(id),
      jsonRequest("PUT", requestEnvelope, MAC_TOKEN),
    );
    expect(response.status).toBe(201);
    expectHardened(response);

    response = await fetchPath(
      requestPath(id),
      jsonRequest("PUT", requestEnvelope, MAC_TOKEN),
    );
    expect(response.status).toBe(200);
    expectHardened(response);

    response = await fetchPath(
      `/v1/mailboxes/${MAILBOX}/requests/next`,
      { headers: auth(PANEL_TOKEN) },
    );
    expect(response.status).toBe(200);
    expectHardened(response);
    const pending = await response.json() as Record<string, unknown>;
    expect(pending.requestId).toBe(id);
    expect(pending.expiresAtMs).toEqual(expect.any(Number));
    expect(pending.envelope).toEqual(JSON.parse(requestEnvelope));

    response = await fetchPath(
      verdictPath(id),
      jsonRequest("POST", verdictEnvelope, PANEL_TOKEN),
    );
    expect(response.status).toBe(201);
    expectHardened(response);

    response = await fetchPath(
      verdictPath(id),
      jsonRequest("POST", verdictEnvelope, PANEL_TOKEN),
    );
    expect(response.status).toBe(200);
    expectHardened(response);

    response = await fetchPath(
      `/v1/mailboxes/${MAILBOX}/verdicts`,
      { headers: auth(MAC_TOKEN) },
    );
    expect(response.status).toBe(200);
    expectHardened(response);
    const verdicts = await response.json() as { verdicts: unknown[] };
    expect(verdicts.verdicts).toEqual([{
      requestId: id,
      envelope: JSON.parse(verdictEnvelope),
      verdictAtMs: expect.any(Number),
    }]);

    response = await fetchPath(requestPath(id), {
      method: "DELETE",
      headers: auth(MAC_TOKEN),
    });
    expect(response.status).toBe(204);
    expectHardened(response);

    for (const [path, token] of [
      [`/v1/mailboxes/${MAILBOX}/requests/next`, PANEL_TOKEN],
      [`/v1/mailboxes/${MAILBOX}/verdicts`, MAC_TOKEN],
    ] as const) {
      response = await fetchPath(path, { headers: auth(token) });
      expect(response.status).toBe(204);
      expect(await response.text()).toBe("");
      expectHardened(response);
    }
  });

  it("maps conflicting bodies and mailbox capacity without replacement", async () => {
    const firstId = requestId();
    const original = envelope(REQUEST_CIPHERTEXT_BYTES, 0x10);
    const changed = envelope(REQUEST_CIPHERTEXT_BYTES, 0x11);
    await fetchPath(requestPath(firstId), jsonRequest("PUT", original, MAC_TOKEN));

    let response = await fetchPath(
      requestPath(firstId),
      jsonRequest("PUT", changed, MAC_TOKEN),
    );
    expect(response.status).toBe(409);
    expectHardened(response);

    for (let index = 2; index <= 8; index += 1) {
      response = await fetchPath(
        requestPath(requestId(index)),
        jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES, index), MAC_TOKEN),
      );
      expect(response.status).toBe(201);
    }
    response = await fetchPath(
      requestPath(requestId(9)),
      jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES, 9), MAC_TOKEN),
    );
    expect(response.status).toBe(429);
    expectHardened(response);

    response = await fetchPath(
      verdictPath(firstId),
      jsonRequest("POST", envelope(VERDICT_CIPHERTEXT_BYTES), PANEL_TOKEN),
    );
    expect(response.status).toBe(201);
    response = await fetchPath(
      verdictPath(firstId),
      jsonRequest("POST", envelope(VERDICT_CIPHERTEXT_BYTES, 0x12), PANEL_TOKEN),
    );
    expect(response.status).toBe(409);
    expectHardened(response);
  });

  it("requires a live request for verdicts and keeps deletion idempotent", async () => {
    const id = requestId();
    let response = await fetchPath(
      verdictPath(id),
      jsonRequest("POST", envelope(VERDICT_CIPHERTEXT_BYTES), PANEL_TOKEN),
    );
    expect(response.status).toBe(404);
    expect(await response.text()).toBe("Not found");
    expectHardened(response);

    response = await fetchPath(requestPath(id), {
      method: "DELETE",
      headers: auth(MAC_TOKEN),
    });
    expect(response.status).toBe(204);
    expectHardened(response);
  });

  it("returns one oldest verdict so every poll stays below 4096 bytes", async () => {
    const verdictBody = envelope(VERDICT_CIPHERTEXT_BYTES);
    for (let index = 1; index <= 3; index += 1) {
      const id = requestId(index);
      await fetchPath(
        requestPath(id),
        jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES, index), MAC_TOKEN),
      );
      await fetchPath(
        verdictPath(id),
        jsonRequest("POST", verdictBody, PANEL_TOKEN),
      );
    }

    let response = await fetchPath(
      `/v1/mailboxes/${MAILBOX}/verdicts`,
      { headers: auth(MAC_TOKEN) },
    );
    const firstBody = await response.text();
    expect(new TextEncoder().encode(firstBody).byteLength).toBeLessThan(4096);
    expect((JSON.parse(firstBody) as { verdicts: Array<{ requestId: string }> })
      .verdicts.map((item) => item.requestId)).toEqual([requestId(1)]);

    await fetchPath(requestPath(requestId(1)), {
      method: "DELETE",
      headers: auth(MAC_TOKEN),
    });
    response = await fetchPath(
      `/v1/mailboxes/${MAILBOX}/verdicts`,
      { headers: auth(MAC_TOKEN) },
    );
    expect((await response.json() as {
      verdicts: Array<{ requestId: string }>;
    }).verdicts.map((item) => item.requestId)).toEqual([requestId(2)]);
  });

  it("keeps Mac and panel roles separate and hides mailbox mismatches", async () => {
    const cases: Array<[string, RequestInit | undefined]> = [
      [requestPath(), jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES), PANEL_TOKEN)],
      [`/v1/mailboxes/${MAILBOX}/requests/next`, { headers: auth(MAC_TOKEN) }],
      [verdictPath(), jsonRequest("POST", envelope(VERDICT_CIPHERTEXT_BYTES), MAC_TOKEN)],
      [`/v1/mailboxes/${MAILBOX}/verdicts`, { headers: auth(PANEL_TOKEN) }],
      [requestPath(), { method: "DELETE", headers: auth(PANEL_TOKEN) }],
      [requestPath(), jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES), "wrong")],
      [requestPath(), {
        method: "PUT",
        body: envelope(REQUEST_CIPHERTEXT_BYTES),
        headers: { "Content-Type": "application/json" },
      }],
      [requestPath(), {
        method: "PUT",
        body: envelope(REQUEST_CIPHERTEXT_BYTES),
        headers: {
          Authorization: `Basic ${MAC_TOKEN}`,
          "Content-Type": "application/json",
        },
      }],
      [requestPath(), {
        method: "PUT",
        body: envelope(REQUEST_CIPHERTEXT_BYTES),
        headers: {
          Authorization: `Bearer  ${MAC_TOKEN}`,
          "Content-Type": "application/json",
        },
      }],
      [requestPath().replace(MAILBOX, OTHER_MAILBOX),
        jsonRequest("PUT", envelope(REQUEST_CIPHERTEXT_BYTES), MAC_TOKEN)],
    ];

    for (const [path, init] of cases) {
      const response = await fetchPath(path, init);
      expect(response.status, path).toBe(404);
      expect(await response.text()).toBe("Not found");
      expectHardened(response);
    }
  });

  it("returns 405 for known routes with unsupported methods", async () => {
    const cases: Array<[string, string, string]> = [
      [requestPath(), "GET", MAC_TOKEN],
      [requestPath(), "POST", MAC_TOKEN],
      [`/v1/mailboxes/${MAILBOX}/requests/next`, "PUT", PANEL_TOKEN],
      [verdictPath(), "PUT", PANEL_TOKEN],
      [`/v1/mailboxes/${MAILBOX}/verdicts`, "POST", MAC_TOKEN],
    ];
    for (const [path, method, token] of cases) {
      const response = await fetchPath(path, { method, headers: auth(token) });
      expect(response.status, `${method} ${path}`).toBe(405);
      expectHardened(response);
    }
  });

  it("requires application/json for body-bearing routes", async () => {
    for (const [path, method, body, token] of [
      [requestPath(), "PUT", envelope(REQUEST_CIPHERTEXT_BYTES), MAC_TOKEN],
      [verdictPath(), "POST", envelope(VERDICT_CIPHERTEXT_BYTES), PANEL_TOKEN],
    ] as const) {
      for (const contentType of ["text/plain", "application/cbor", ""] as const) {
        const headers = auth(token);
        if (contentType !== "") {
          headers["Content-Type"] = contentType;
        }
        const response = await fetchPath(path, { method, body, headers });
        expect(response.status).toBe(415);
        expectHardened(response);
      }
      const duplicate = await fetchPath(path, {
        method,
        body,
        headers: {
          ...auth(token),
          "Content-Type": "application/json, application/json",
        },
      });
      expect(duplicate.status).toBe(415);
      expectHardened(duplicate);
      const accepted = await fetchPath(path, jsonRequest(
        method,
        body,
        token,
        { "Content-Type": "application/json; charset=UTF-8" },
      ));
      expect([200, 201]).toContain(accepted.status);
      expectHardened(accepted);
    }
  });

  it("rejects non-canonical, extra, duplicate, and malformed envelopes", async () => {
    const valid = JSON.parse(envelope(REQUEST_CIPHERTEXT_BYTES)) as {
      ciphertext: string;
      nonce: string;
      v: number;
    };
    const invalidBodies = [
      "{}",
      "[]",
      "not-json",
      `${envelope(REQUEST_CIPHERTEXT_BYTES)} `,
      JSON.stringify({ ...valid, extra: true }),
      JSON.stringify({ ciphertext: valid.ciphertext, nonce: valid.nonce, v: 2 }),
      JSON.stringify({ ciphertext: valid.ciphertext, nonce: valid.nonce, v: true }),
      JSON.stringify({ v: 1, nonce: valid.nonce, ciphertext: valid.ciphertext }),
      `{"ciphertext":"${valid.ciphertext}","nonce":"${valid.nonce}","v":1,"v":1}`,
      JSON.stringify({ ciphertext: "AA", nonce: valid.nonce, v: 1 }),
      JSON.stringify({ ciphertext: valid.ciphertext, nonce: "AA", v: 1 }),
      JSON.stringify({ ciphertext: `${valid.ciphertext}=`, nonce: valid.nonce, v: 1 }),
      JSON.stringify({ ciphertext: valid.ciphertext, nonce: `${valid.nonce}+`, v: 1 }),
    ];
    for (const body of invalidBodies) {
      const response = await fetchPath(
        requestPath(),
        jsonRequest("PUT", body, MAC_TOKEN),
      );
      expect(response.status, body.slice(0, 80)).toBe(400);
      expectHardened(response);
    }

    const invalidUtf8 = new Uint8Array([0x7b, 0xff, 0x7d]);
    const response = await fetchPath(
      requestPath(),
      jsonRequest("PUT", invalidUtf8, MAC_TOKEN),
    );
    expect(response.status).toBe(400);
    expectHardened(response);

    const validBytes = new TextEncoder().encode(
      envelope(REQUEST_CIPHERTEXT_BYTES),
    );
    const bomPrefixed = new Uint8Array(validBytes.byteLength + 3);
    bomPrefixed.set([0xef, 0xbb, 0xbf]);
    bomPrefixed.set(validBytes, 3);
    const bomResponse = await fetchPath(
      requestPath(),
      jsonRequest("PUT", bomPrefixed, MAC_TOKEN),
    );
    expect(bomResponse.status).toBe(400);
    expectHardened(bomResponse);
  });

  it("validates request and verdict ciphertext sizes independently", async () => {
    for (const size of [VERDICT_CIPHERTEXT_BYTES, REQUEST_CIPHERTEXT_BYTES - 1,
                        REQUEST_CIPHERTEXT_BYTES + 1]) {
      const response = await fetchPath(
        requestPath(),
        jsonRequest("PUT", envelope(size), MAC_TOKEN),
      );
      expect(response.status).toBe(400);
      expectHardened(response);
    }
    for (const size of [REQUEST_CIPHERTEXT_BYTES, VERDICT_CIPHERTEXT_BYTES - 1,
                        VERDICT_CIPHERTEXT_BYTES + 1]) {
      const response = await fetchPath(
        verdictPath(),
        jsonRequest("POST", envelope(size), PANEL_TOKEN),
      );
      expect(response.status).toBe(400);
      expectHardened(response);
    }
    const nonCanonical = JSON.parse(envelope(VERDICT_CIPHERTEXT_BYTES)) as {
      ciphertext: string;
      nonce: string;
      v: 1;
    };
    nonCanonical.ciphertext = `${nonCanonical.ciphertext.slice(0, -1)}B`;
    const response = await fetchPath(
      verdictPath(),
      jsonRequest("POST", JSON.stringify(nonCanonical), PANEL_TOKEN),
    );
    expect(response.status).toBe(400);
    expectHardened(response);
  });

  it("rejects declared and streamed bodies above 4096 bytes", async () => {
    let response = await fetchPath(requestPath(), jsonRequest(
      "PUT",
      "{}",
      MAC_TOKEN,
      { "Content-Length": "4097" },
    ));
    expect(response.status).toBe(413);
    expectHardened(response);

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array(2_500));
        controller.enqueue(new Uint8Array(2_500));
        controller.close();
      },
    });
    response = await fetchPath(
      requestPath(),
      jsonRequest("PUT", stream, MAC_TOKEN),
    );
    expect(response.status).toBe(413);
    expectHardened(response);
  });

  it("rejects malformed Content-Length without reading the body", async () => {
    for (const contentLength of ["-1", "+1", "01", "1, 1", "1.0"]) {
      const response = await fetchPath(requestPath(), jsonRequest(
        "PUT",
        envelope(REQUEST_CIPHERTEXT_BYTES),
        MAC_TOKEN,
        { "Content-Length": contentLength },
      ));
      expect(response.status, contentLength).toBe(400);
      expectHardened(response);
    }
  });

  it("rejects path and request-ID injection without decoding aliases", async () => {
    const paths = [
      `/v1/mailboxes/${MAILBOX}/requests/not-an-id`,
      `/v1/mailboxes/${MAILBOX}/requests/${requestId()}%2Fverdict`,
      `/v1/mailboxes/${MAILBOX}/requests/${requestId()}%00`,
      `/v1/mailboxes/${MAILBOX}/requests/${"A".repeat(21)}B`,
      `/v1/mailboxes/${MAILBOX}/requests/${requestId()}/verdict/extra`,
      `/v1/mailboxes/${MAILBOX}/requests//${requestId()}`,
      `${requestPath()}?mailbox=${OTHER_MAILBOX}`,
    ];
    for (const path of paths) {
      const response = await fetchPath(path, {
        method: "PUT",
        headers: auth(MAC_TOKEN),
      });
      expect(response.status, path).toBe(404);
      expectHardened(response);
    }
  });

  it("returns 404 with hardened headers for unknown routes", async () => {
    for (const path of ["/", "/v1", "/v1/mailboxes", "/favicon.ico"]) {
      const response = await fetchPath(path);
      expect(response.status).toBe(404);
      expectHardened(response);
    }
  });

  it("logs only bounded structural metadata", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const id = requestId();
    const body = envelope(REQUEST_CIPHERTEXT_BYTES);
    const response = await fetchPath(
      requestPath(id),
      jsonRequest("PUT", body, MAC_TOKEN),
    );
    expect(response.status).toBe(201);
    expect(log).toHaveBeenCalledTimes(1);
    const line = String(log.mock.calls[0]?.[0]);
    expect(JSON.parse(line)).toMatchObject({
      event: "interaction_relay_request",
      route: "put_request",
      status: 201,
    });
    for (const secret of [MAC_TOKEN, PANEL_TOKEN, MAILBOX, id, body]) {
      expect(line).not.toContain(secret);
    }
  });
});
