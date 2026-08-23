/*
 * Brevlådans sammanslagning, hållen stilla med node --test (ingen
 * Cloudflare behövs): färskast vinner PER POOL för /api/tokens, nyast
 * dokument för resten, och döda/korrupta dokument tystar aldrig de andra.
 *
 * Körs av test/run.sh när node finns; CI:s numbers-relay-jobb kör den via
 * "node --test tools/relay/".
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mergeTokens, newestBody } from "./merge.js";

test("en ensam avsändare passerar orörd", () => {
  const doc = { receivedAt: 100, publisher: "mac",
                body: { v: 2, weekPct: 73, weekObservedAt: 90 } };
  assert.deepEqual(mergeTokens([doc]), doc.body);
});

test("varje pool tas från den maskin som såg den senast", () => {
  const mac = { receivedAt: 200, publisher: "mac", body: {
    v: 2,
    claudeWeekPct: 70, claudeWeekStale: true,
    claudeWeekObservedAt: 150,               // äldre Claude-observation
    codexWeekPct: 41, codexWeekObservedAt: 190,  // färsk Codex (Macen kör Codex)
  } };
  const pc = { receivedAt: 210, publisher: "pc", body: {
    v: 2,
    claudeWeekPct: 73, claudeWeekStale: false,
    claudeWeekObservedAt: 205,               // färsk Claude (PC:n frågade nyss)
    codexWeekPct: 39, codexWeekObservedAt: 100,  // gammal Codex
  } };
  const merged = mergeTokens([mac, pc]);
  assert.equal(merged.claudeWeekPct, 73, "Claude ska komma från PC:n");
  assert.equal(merged.claudeWeekStale, false,
               "PC:ns färska Claude-status ska följa poolen");
  assert.equal(merged.claudeWeekObservedAt, 205,
               "Claude-stämpeln ska följa PC:ns pool");
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
