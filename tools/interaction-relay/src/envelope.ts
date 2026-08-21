export const MAX_ENVELOPE_BYTES = 4096;
export const REQUEST_CIPHERTEXT_BYTES = 2048 + 16;
export const VERDICT_CIPHERTEXT_BYTES = 1024 + 16;
export const STATUS_CIPHERTEXT_BYTES = 2816 + 16;

const BASE64URL_RE = /^[A-Za-z0-9_-]*$/;
const JSON_CONTENT_TYPE_RE =
  /^application\/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?$/i;

export interface OuterEnvelope {
  ciphertext: string;
  nonce: string;
  v: 1;
}

export type EnvelopeReadResult =
  | { ok: true; envelope: OuterEnvelope; text: string }
  | { ok: false; status: 400 | 413 | 415 };

export async function readEnvelope(
  request: Request,
  ciphertextBytes: number,
): Promise<EnvelopeReadResult> {
  if (!isJsonContentType(request.headers.get("Content-Type"))) {
    return { ok: false, status: 415 };
  }

  const declaredLength = request.headers.get("Content-Length");
  if (declaredLength !== null) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(declaredLength)) {
      return { ok: false, status: 400 };
    }
    if (Number(declaredLength) > MAX_ENVELOPE_BYTES) {
      await cancelBody(request.body);
      return { ok: false, status: 413 };
    }
  }

  const bytes = await readBoundedBody(request.body);
  if (bytes === "too-large") {
    return { ok: false, status: 413 };
  }
  if (bytes === null || bytes.byteLength === 0) {
    return { ok: false, status: 400 };
  }
  if (bytes.byteLength >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb &&
      bytes[2] === 0xbf) {
    return { ok: false, status: 400 };
  }

  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: false })
      .decode(bytes);
  } catch {
    return { ok: false, status: 400 };
  }

  const envelope = parseEnvelope(text, ciphertextBytes);
  return envelope === null
    ? { ok: false, status: 400 }
    : { ok: true, envelope, text };
}

export function isMailboxId(value: string): boolean {
  return /^vp_[A-Za-z0-9_-]{16}$/.test(value);
}

export function isRequestId(value: string): boolean {
  const bytes = decodeBase64url(value);
  return bytes !== null && bytes.byteLength === 16;
}

export function isBearerToken(value: string): boolean {
  const bytes = decodeBase64url(value);
  return bytes !== null && bytes.byteLength === 32;
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
}

function isJsonContentType(value: string | null): boolean {
  return value !== null && JSON_CONTENT_TYPE_RE.test(value);
}

async function readBoundedBody(
  body: ReadableStream<Uint8Array> | null,
): Promise<Uint8Array | "too-large" | null> {
  if (body === null) {
    return null;
  }
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > MAX_ENVELOPE_BYTES) {
        try {
          await reader.cancel();
        } catch {
          // The size decision is already final.
        }
        return "too-large";
      }
      chunks.push(value);
    }
  } catch {
    return null;
  } finally {
    reader.releaseLock();
  }

  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined;
}

async function cancelBody(body: ReadableStream<Uint8Array> | null): Promise<void> {
  if (body === null) {
    return;
  }
  try {
    await body.cancel();
  } catch {
    // The response remains a deterministic 413 even if cancellation races EOF.
  }
}

function parseEnvelope(
  text: string,
  ciphertextBytes: number,
): OuterEnvelope | null {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(value) || Object.keys(value).length !== 3 ||
      typeof value.ciphertext !== "string" ||
      typeof value.nonce !== "string" ||
      typeof value.v !== "number" || value.v !== 1) {
    return null;
  }

  const envelope: OuterEnvelope = {
    ciphertext: value.ciphertext,
    nonce: value.nonce,
    v: 1,
  };
  if (JSON.stringify(envelope) !== text) {
    return null;
  }
  const nonce = decodeBase64url(envelope.nonce);
  const ciphertext = decodeBase64url(envelope.ciphertext);
  if (nonce === null || nonce.byteLength !== 12 ||
      ciphertext === null || ciphertext.byteLength !== ciphertextBytes) {
    return null;
  }
  return envelope;
}

function decodeBase64url(value: string): Uint8Array | null {
  if (!BASE64URL_RE.test(value) || value.length % 4 === 1) {
    return null;
  }
  let binary: string;
  try {
    binary = atob(value.replaceAll("-", "+").replaceAll("_", "/") +
      "=".repeat((4 - value.length % 4) % 4));
  } catch {
    return null;
  }
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (encodeBase64url(bytes) !== value) {
    return null;
  }
  return bytes;
}

function encodeBase64url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_")
    .replace(/=+$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
