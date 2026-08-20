import { DurableObject } from "cloudflare:workers";

const REQUEST_TTL_MS = 120_000;
const MAX_LIVE_REQUESTS = 8;

export type PutRequestResult = "created" | "existing" | "conflict" | "full";
export type PutVerdictResult = "created" | "existing" | "conflict" | "missing";
export type DeleteRequestResult = "deleted" | "missing";

export interface PendingRequest {
  requestId: string;
  envelope: string;
  expiresAtMs: number;
}

export interface StoredVerdict {
  requestId: string;
  envelope: string;
  verdictAtMs: number;
}

interface RequestRow extends Record<string, SqlStorageValue> {
  request_id: string;
  request_envelope: string;
  request_hash: string;
  expires_at_ms: number;
  verdict_envelope: string | null;
  verdict_hash: string | null;
  verdict_at_ms: number | null;
}

export class InteractionMailbox extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS requests (
          request_id TEXT PRIMARY KEY,
          request_envelope TEXT NOT NULL,
          request_hash TEXT NOT NULL,
          created_at_ms INTEGER NOT NULL,
          expires_at_ms INTEGER NOT NULL,
          verdict_envelope TEXT,
          verdict_hash TEXT,
          verdict_at_ms INTEGER
        )
      `);
      ctx.storage.sql.exec(`
        CREATE INDEX IF NOT EXISTS requests_expiry_created
        ON requests (expires_at_ms, created_at_ms)
      `);
    });
  }

  async putRequest(
    requestId: string,
    envelope: string,
    hash: string,
    nowMs: number,
  ): Promise<PutRequestResult> {
    assertNowMs(nowMs);
    const result = this.ctx.storage.transactionSync<PutRequestResult>(() => {
      this.deleteExpired(nowMs);
      const existing = this.ctx.storage.sql.exec<RequestRow>(`
        SELECT request_id, request_envelope, request_hash, expires_at_ms,
               verdict_envelope, verdict_hash, verdict_at_ms
        FROM requests WHERE request_id = ?
      `, requestId).toArray()[0];
      if (existing !== undefined) {
        return existing.request_envelope === envelope &&
          existing.request_hash === hash
          ? "existing"
          : "conflict";
      }

      const count = this.ctx.storage.sql.exec<{ count: number }>(
        "SELECT COUNT(*) AS count FROM requests",
      ).one().count;
      if (count >= MAX_LIVE_REQUESTS) {
        return "full";
      }

      this.ctx.storage.sql.exec(`
        INSERT INTO requests (
          request_id, request_envelope, request_hash,
          created_at_ms, expires_at_ms
        ) VALUES (?, ?, ?, ?, ?)
      `, requestId, envelope, hash, nowMs, nowMs + REQUEST_TTL_MS);
      return "created";
    });
    await this.scheduleNextAlarm();
    return result;
  }

  async nextRequest(nowMs: number): Promise<PendingRequest | null> {
    assertNowMs(nowMs);
    const result = this.ctx.storage.transactionSync<PendingRequest | null>(() => {
      this.deleteExpired(nowMs);
      const row = this.ctx.storage.sql.exec<RequestRow>(`
        SELECT request_id, request_envelope, request_hash, expires_at_ms,
               verdict_envelope, verdict_hash, verdict_at_ms
        FROM requests
        ORDER BY created_at_ms ASC, request_id ASC
        LIMIT 1
      `).toArray()[0];
      return row === undefined ? null : {
        requestId: row.request_id,
        envelope: row.request_envelope,
        expiresAtMs: row.expires_at_ms,
      };
    });
    await this.scheduleNextAlarm();
    return result;
  }

  async putVerdict(
    requestId: string,
    envelope: string,
    hash: string,
    nowMs: number,
  ): Promise<PutVerdictResult> {
    assertNowMs(nowMs);
    const result = this.ctx.storage.transactionSync<PutVerdictResult>(() => {
      this.deleteExpired(nowMs);
      const existing = this.ctx.storage.sql.exec<RequestRow>(`
        SELECT request_id, request_envelope, request_hash, expires_at_ms,
               verdict_envelope, verdict_hash, verdict_at_ms
        FROM requests WHERE request_id = ?
      `, requestId).toArray()[0];
      if (existing === undefined) {
        return "missing";
      }
      if (existing.verdict_envelope !== null || existing.verdict_hash !== null) {
        return existing.verdict_envelope === envelope &&
          existing.verdict_hash === hash
          ? "existing"
          : "conflict";
      }

      this.ctx.storage.sql.exec(`
        UPDATE requests
        SET verdict_envelope = ?, verdict_hash = ?, verdict_at_ms = ?
        WHERE request_id = ?
      `, envelope, hash, nowMs, requestId);
      return "created";
    });
    await this.scheduleNextAlarm();
    return result;
  }

  async listVerdicts(nowMs: number): Promise<StoredVerdict[]> {
    assertNowMs(nowMs);
    const result = this.ctx.storage.transactionSync<StoredVerdict[]>(() => {
      this.deleteExpired(nowMs);
      return this.ctx.storage.sql.exec<RequestRow>(`
        SELECT request_id, request_envelope, request_hash, expires_at_ms,
               verdict_envelope, verdict_hash, verdict_at_ms
        FROM requests
        WHERE verdict_envelope IS NOT NULL
          AND verdict_hash IS NOT NULL
          AND verdict_at_ms IS NOT NULL
        ORDER BY verdict_at_ms ASC, request_id ASC
      `).toArray().map((row) => ({
        requestId: row.request_id,
        envelope: row.verdict_envelope as string,
        verdictAtMs: row.verdict_at_ms as number,
      }));
    });
    await this.scheduleNextAlarm();
    return result;
  }

  async deleteRequest(
    requestId: string,
    nowMs: number,
  ): Promise<DeleteRequestResult> {
    assertNowMs(nowMs);
    const result = this.ctx.storage.transactionSync<DeleteRequestResult>(() => {
      this.deleteExpired(nowMs);
      const deleted = this.ctx.storage.sql.exec(
        "DELETE FROM requests WHERE request_id = ?",
        requestId,
      ).rowsWritten;
      return deleted === 0 ? "missing" : "deleted";
    });
    await this.scheduleNextAlarm();
    return result;
  }

  async alarm(): Promise<void> {
    const nowMs = Date.now();
    this.ctx.storage.transactionSync(() => this.deleteExpired(nowMs));
    await this.scheduleNextAlarm();
  }

  private deleteExpired(nowMs: number): void {
    this.ctx.storage.sql.exec(
      "DELETE FROM requests WHERE expires_at_ms <= ?",
      nowMs,
    );
  }

  private async scheduleNextAlarm(): Promise<void> {
    const row = this.ctx.storage.sql.exec<{ expires_at_ms: number | null }>(
      "SELECT MIN(expires_at_ms) AS expires_at_ms FROM requests",
    ).one();
    if (row.expires_at_ms === null) {
      await this.ctx.storage.deleteAlarm();
      return;
    }
    await this.ctx.storage.setAlarm(row.expires_at_ms);
  }
}

function assertNowMs(nowMs: number): void {
  if (!Number.isSafeInteger(nowMs) || nowMs < 0 ||
      nowMs > Number.MAX_SAFE_INTEGER - REQUEST_TTL_MS) {
    throw new RangeError("invalid server time");
  }
}
