import { env } from "cloudflare:workers";
import {
  evictDurableObject,
  runDurableObjectAlarm,
  runInDurableObject,
} from "cloudflare:test";
import { describe, expect, it } from "vitest";

const TTL_MS = 120_000;
let mailboxSequence = 0;

function mailbox() {
  mailboxSequence += 1;
  return env.INTERACTION_MAILBOX.getByName(`mailbox-test-${mailboxSequence}`);
}

describe("InteractionMailbox", () => {
  it("creates once and accepts only an exact idempotent retry", async () => {
    const stub = mailbox();
    const now = Date.now();

    await expect(stub.putRequest("request-a", "envelope-a", "hash-a", now))
      .resolves.toBe("created");
    await expect(stub.putRequest("request-a", "envelope-a", "hash-a", now + 5_000))
      .resolves.toBe("existing");
    await expect(stub.putRequest("request-a", "envelope-b", "hash-a", now + 5_000))
      .resolves.toBe("conflict");
    await expect(stub.putRequest("request-a", "envelope-a", "hash-b", now + 5_000))
      .resolves.toBe("conflict");

    await expect(stub.nextRequest(now + 5_000)).resolves.toEqual({
      requestId: "request-a",
      envelope: "envelope-a",
      expiresAtMs: now + TTL_MS,
    });
  });

  it("caps the mailbox at eight live requests without breaking retries", async () => {
    const stub = mailbox();
    const now = Date.now();

    for (let index = 0; index < 8; index += 1) {
      await expect(stub.putRequest(
        `request-${index}`,
        `envelope-${index}`,
        `hash-${index}`,
        now + index,
      )).resolves.toBe("created");
    }

    await expect(stub.putRequest("request-8", "envelope-8", "hash-8", now + 8))
      .resolves.toBe("full");
    await expect(stub.putRequest("request-0", "envelope-0", "hash-0", now + 9))
      .resolves.toBe("existing");
  });

  it("serializes concurrent create-once and capacity decisions", async () => {
    const sameIdStub = mailbox();
    const now = Date.now();
    const sameIdResults = await Promise.all([
      sameIdStub.putRequest("same", "envelope-a", "hash-a", now),
      sameIdStub.putRequest("same", "envelope-b", "hash-b", now),
    ]);
    expect(sameIdResults.sort()).toEqual(["conflict", "created"]);

    const capacityStub = mailbox();
    const capacityResults = await Promise.all(
      Array.from({ length: 9 }, (_unused, index) => capacityStub.putRequest(
        `request-${index}`,
        `envelope-${index}`,
        `hash-${index}`,
        now + index,
      )),
    );
    expect(capacityResults.filter((result) => result === "created")).toHaveLength(8);
    expect(capacityResults.filter((result) => result === "full")).toHaveLength(1);
  });

  it("returns the oldest live request and excludes expired rows", async () => {
    const stub = mailbox();
    const now = Date.now();

    await stub.putRequest("oldest", "envelope-old", "hash-old", now);
    await stub.putRequest("newer", "envelope-new", "hash-new", now + 1_000);

    await expect(stub.nextRequest(now + 2_000)).resolves.toMatchObject({
      requestId: "oldest",
    });
    await expect(stub.nextRequest(now + TTL_MS + 500)).resolves.toMatchObject({
      requestId: "newer",
    });
    await expect(stub.nextRequest(now + TTL_MS + 1_000)).resolves.toBeNull();
  });

  it("requires a live request before accepting a verdict", async () => {
    const stub = mailbox();
    const now = Date.now();

    await expect(stub.putVerdict("missing", "verdict", "hash", now))
      .resolves.toBe("missing");
    await stub.putRequest("expired", "request", "request-hash", now);
    await expect(stub.putVerdict(
      "expired",
      "verdict",
      "verdict-hash",
      now + TTL_MS,
    )).resolves.toBe("missing");
  });

  it("stores one verdict and accepts only an exact retry", async () => {
    const stub = mailbox();
    const now = Date.now();
    await stub.putRequest("request-a", "request", "request-hash", now);

    await expect(stub.putVerdict("request-a", "verdict-a", "hash-a", now + 1))
      .resolves.toBe("created");
    await expect(stub.putVerdict("request-a", "verdict-a", "hash-a", now + 2))
      .resolves.toBe("existing");
    await expect(stub.putVerdict("request-a", "verdict-b", "hash-a", now + 2))
      .resolves.toBe("conflict");
    await expect(stub.putVerdict("request-a", "verdict-a", "hash-b", now + 2))
      .resolves.toBe("conflict");

    await expect(stub.listVerdicts(now + 3)).resolves.toEqual([{
      requestId: "request-a",
      envelope: "verdict-a",
      verdictAtMs: now + 1,
    }]);
  });

  it("deletes a request and its verdict atomically", async () => {
    const stub = mailbox();
    const now = Date.now();
    await stub.putRequest("request-a", "request", "request-hash", now);
    await stub.putVerdict("request-a", "verdict", "verdict-hash", now + 1);

    await expect(stub.deleteRequest("request-a", now + 2))
      .resolves.toBe("deleted");
    await expect(stub.nextRequest(now + 3)).resolves.toBeNull();
    await expect(stub.listVerdicts(now + 3)).resolves.toEqual([]);
    await expect(stub.deleteRequest("request-a", now + 4))
      .resolves.toBe("missing");
  });

  it("retains rows across object eviction", async () => {
    const stub = mailbox();
    const now = Date.now();
    await stub.putRequest("request-a", "request", "request-hash", now);

    await evictDurableObject(stub);

    await expect(stub.nextRequest(now + 1)).resolves.toMatchObject({
      requestId: "request-a",
      envelope: "request",
    });
  });

  it("cleans expired rows on alarm and schedules the next expiry", async () => {
    const stub = mailbox();
    const now = Date.now();
    await stub.putRequest("expired", "request-old", "hash-old", now);
    await stub.putRequest("live", "request-new", "hash-new", now + 1);

    const expiredAt = Date.now() - 1;
    const liveUntil = Date.now() + 60_000;
    await runInDurableObject(stub, async (_instance, state) => {
      state.storage.sql.exec(
        "UPDATE requests SET expires_at_ms = ? WHERE request_id = ?",
        expiredAt,
        "expired",
      );
      state.storage.sql.exec(
        "UPDATE requests SET expires_at_ms = ? WHERE request_id = ?",
        liveUntil,
        "live",
      );
      await state.storage.setAlarm(liveUntil);
    });

    await expect(runDurableObjectAlarm(stub)).resolves.toBe(true);

    const state = await runInDurableObject(stub, async (_instance, objectState) => ({
      ids: objectState.storage.sql
        .exec<{ request_id: string }>(
          "SELECT request_id FROM requests ORDER BY request_id",
        )
        .toArray()
        .map((row) => row.request_id),
      alarm: await objectState.storage.getAlarm(),
    }));
    expect(state).toEqual({ ids: ["live"], alarm: liveUntil });
  });
});
