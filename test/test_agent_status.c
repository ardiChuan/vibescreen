/* Strict contract tests for VibePulse agent-status v2. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../components/app_tokens/agent_status_parse.h"

static int failures;

static void check(const char *what, int condition) {
  if (!condition) {
    printf("FAIL %s\n", what);
    failures++;
  }
}

static char *read_file(const char *path, size_t *len_out) {
  FILE *stream = fopen(path, "rb");
  if (!stream) {
    printf("FAIL kan inte läsa %s\n", path);
    failures++;
    return NULL;
  }
  fseek(stream, 0, SEEK_END);
  long length = ftell(stream);
  fseek(stream, 0, SEEK_SET);
  char *data = malloc((size_t)length + 1);
  if (!data) {
    fclose(stream);
    failures++;
    return NULL;
  }
  if (fread(data, 1, (size_t)length, stream) != (size_t)length) {
    printf("FAIL kan inte läsa %s\n", path);
    failures++;
    free(data);
    fclose(stream);
    return NULL;
  }
  data[length] = '\0';
  fclose(stream);
  *len_out = (size_t)length;
  return data;
}

static void rejected_unchanged(const char *what, const char *json,
                               tk_agent_snapshot *out) {
  memset(out, 0xa5, sizeof *out);
  tk_agent_snapshot before;
  memcpy(&before, out, sizeof before);
  if (tk_agent_status_parse(json, strlen(json), out)) {
    printf("FAIL %s accepterades\n", what);
    failures++;
  }
  if (memcmp(&before, out, sizeof before) != 0) {
    printf("FAIL %s rörde utdata\n", what);
    failures++;
  }
}

#define PARSE(JSON, OUT) tk_agent_status_parse((JSON), strlen(JSON), (OUT))

#define WORKING_JOB \
  "{\"task_id\":\"claude-task\",\"event_id\":\"claude-event\"," \
  "\"state\":\"working\",\"project\":\"Torget\"," \
  "\"activity\":\"editing\",\"model\":\"FABLE 5\"," \
  "\"effort\":\"XHIGH\",\"updated_ms\":25}"

#define CODEX_JOB \
  "{\"task_id\":\"codex-task\",\"event_id\":\"codex-event\"," \
  "\"state\":\"working\",\"project\":\"Buddy\"," \
  "\"activity\":\"testing\",\"model\":\"GPT-5.6 SOL\"," \
  "\"effort\":\"XHIGH\",\"updated_ms\":10}"

#define NO_METADATA_JOB \
  "{\"task_id\":\"plain\",\"event_id\":\"plain-event\"," \
  "\"state\":\"done\",\"project\":null,\"activity\":null," \
  "\"updated_ms\":4294967295}"

#define UNKNOWN_JOB \
  "{\"task_id\":\"unknown\",\"event_id\":\"unknown-event\"," \
  "\"state\":\"reviewing\",\"project\":null," \
  "\"activity\":\"reviewing\",\"updated_ms\":1}"

#define EMPTY_CODEX "\"codex\":{\"active_count\":0,\"jobs\":[]}"
#define ONE_CLAUDE(JOB) \
  "\"claude\":{\"active_count\":1,\"jobs\":[" JOB "]}"
#define PAYLOAD(JOB) \
  "{\"v\":2,\"seq\":7,\"agents\":{" ONE_CLAUDE(JOB) "," \
  EMPTY_CODEX "}}"

int main(void) {
  tk_agent_snapshot snapshot = {0};
  size_t fixture_len = 0;
  char *fixture = read_file(
      FIXTURES_DIR "/agent-status-claude-working.json", &fixture_len);
  if (fixture) {
    check("v2-fixturen parsar",
          tk_agent_status_parse(fixture, fixture_len, &snapshot));
    check("fixturens seq", snapshot.seq == 201);
    check("en Claude-session",
          snapshot.claude.active_count == 1 &&
          snapshot.claude.job_count == 1);
    check("Claude ändrar filer",
          snapshot.claude.jobs[0].state == TK_AGENT_WORKING &&
          snapshot.claude.jobs[0].activity == TK_ACTIVITY_EDITING);
    check("modell, effort och projekt bevaras",
          snapshot.claude.jobs[0].has_model &&
          snapshot.claude.jobs[0].has_effort &&
          strcmp(snapshot.claude.jobs[0].model, "FABLE 5") == 0 &&
          strcmp(snapshot.claude.jobs[0].effort, "XHIGH") == 0 &&
          strcmp(snapshot.claude.jobs[0].project, "Torget") == 0);
    check("Codex-listan är tom",
          snapshot.codex.active_count == 0 &&
          snapshot.codex.job_count == 0);
    free(fixture);
  }

  const char multi[] =
      "{\"v\":2,\"seq\":9,\"agents\":{" \
      "\"claude\":{\"active_count\":5,\"jobs\":[" WORKING_JOB "," \
      "{\"task_id\":\"claude-2\",\"event_id\":\"event-2\"," \
      "\"state\":\"waiting\",\"project\":\"Solelkollen\"," \
      "\"activity\":\"waiting_approval\",\"updated_ms\":5}]}," \
      "\"codex\":{\"active_count\":1,\"jobs\":[" CODEX_JOB "]}}}";
  check("flera jobb parsas", PARSE(multi, &snapshot));
  check("alla aktiva räknas även över listtak",
        snapshot.claude.active_count == 5);
  check("två Claude-jobb lagras", snapshot.claude.job_count == 2);
  check("Codex-projekt bevaras",
        snapshot.codex.job_count == 1 &&
        strcmp(snapshot.codex.jobs[0].project, "Buddy") == 0);

  check("valfri modellmetadata kan saknas",
        PARSE(PAYLOAD(NO_METADATA_JOB), &snapshot));
  check("saknad metadata är explicit",
        !snapshot.claude.jobs[0].has_model &&
        !snapshot.claude.jobs[0].has_effort &&
        snapshot.claude.jobs[0].updated_ms == UINT32_MAX);

  check("framtida enumvärden parsas",
        PARSE(PAYLOAD(UNKNOWN_JOB), &snapshot));
  check("framtida enumvärden mappas till unknown",
        snapshot.claude.jobs[0].state == TK_AGENT_UNKNOWN &&
        snapshot.claude.jobs[0].activity == TK_ACTIVITY_UNKNOWN);

  rejected_unchanged(
      "v1 avvisas",
      "{\"v\":1,\"seq\":7,\"agents\":{" ONE_CLAUDE(WORKING_JOB) "," \
      EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged("error-form", "{\"error\":\"nope\"}", &snapshot);
  rejected_unchanged("skräp efter rot", PAYLOAD(WORKING_JOB) "{}",
                     &snapshot);
  rejected_unchanged("giltig JSON efter rot", PAYLOAD(WORKING_JOB) " []",
                     &snapshot);
  rejected_unchanged("rotarray", "[]", &snapshot);

  rejected_unchanged(
      "fem publika jobb avvisas",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":5,\"jobs\":[" \
      WORKING_JOB "," WORKING_JOB "," WORKING_JOB "," WORKING_JOB "," \
      WORKING_JOB "]}," EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "negativ active_count",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":-1,\"jobs\":[]}," \
      EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "active_count över uint8",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":256,\"jobs\":[]}," \
      EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "fraktionell active_count",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":1.5,\"jobs\":[]}," \
      EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "provider med extrafält",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":0,\"jobs\":[],\"private\":1}," \
      EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "jobb med extrafält",
      PAYLOAD("{\"task_id\":\"a\",\"event_id\":\"b\"," \
              "\"state\":\"working\",\"project\":null," \
              "\"activity\":\"thinking\",\"updated_ms\":0," \
              "\"private\":true}"), &snapshot);
  rejected_unchanged(
      "dubbelt providerfält",
      "{\"v\":2,\"seq\":1,\"agents\":{" ONE_CLAUDE(WORKING_JOB) "," \
      ONE_CLAUDE(WORKING_JOB) "," EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "dubbelt jobsfält",
      "{\"v\":2,\"seq\":1,\"agents\":{" \
      "\"claude\":{\"active_count\":1,\"jobs\":[]," \
      "\"jobs\":[" WORKING_JOB "]}," EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "dubbelt jobbfält",
      PAYLOAD("{\"task_id\":\"a\",\"task_id\":\"b\"," \
              "\"event_id\":\"e\",\"state\":\"working\"," \
              "\"project\":null,\"activity\":\"thinking\"," \
              "\"updated_ms\":0}"), &snapshot);

  rejected_unchanged(
      "för långt projekt",
      PAYLOAD("{\"task_id\":\"a\",\"event_id\":\"e\"," \
              "\"state\":\"working\"," \
              "\"project\":\"12345678901234567\"," \
              "\"activity\":\"thinking\",\"updated_ms\":0}"),
      &snapshot);
  rejected_unchanged(
      "kontrollnolla i projekt",
      PAYLOAD("{\"task_id\":\"a\",\"event_id\":\"e\"," \
              "\"state\":\"working\",\"project\":\"Tor\\u0000get\"," \
              "\"activity\":\"thinking\",\"updated_ms\":0}"),
      &snapshot);
  rejected_unchanged(
      "modell med fel typ",
      PAYLOAD("{\"task_id\":\"a\",\"event_id\":\"e\"," \
              "\"state\":\"working\",\"project\":null," \
              "\"activity\":\"thinking\",\"model\":7," \
              "\"updated_ms\":0}"), &snapshot);
  rejected_unchanged(
      "fraktionell updated_ms",
      PAYLOAD("{\"task_id\":\"a\",\"event_id\":\"e\"," \
              "\"state\":\"working\",\"project\":null," \
              "\"activity\":\"thinking\",\"updated_ms\":1.5}"),
      &snapshot);
  rejected_unchanged(
      "seq över uint32",
      "{\"v\":2,\"seq\":4294967296,\"agents\":{" \
      ONE_CLAUDE(WORKING_JOB) "," EMPTY_CODEX "}}", &snapshot);
  rejected_unchanged(
      "seq med inledande nolla",
      "{\"v\":2,\"seq\":01,\"agents\":{" \
      ONE_CLAUDE(WORKING_JOB) "," EMPTY_CODEX "}}", &snapshot);

  check("omordnade providerfält accepteras",
        PARSE("{\"agents\":{" \
              "\"codex\":{\"jobs\":[],\"active_count\":0}," \
              "\"claude\":{\"jobs\":[" WORKING_JOB "] ," \
              "\"active_count\":1}},\"seq\":11,\"v\":2}",
              &snapshot) && snapshot.seq == 11);
  check("BOM accepteras",
        PARSE("\xEF\xBB\xBF" PAYLOAD(WORKING_JOB), &snapshot));

  check("provider-enum har stabil ordning",
        TK_AGENT_PROVIDER_CLAUDE == 0 && TK_AGENT_PROVIDER_CODEX == 1 &&
        TK_AGENT_PROVIDER_COUNT == 2 && TK_AGENT_JOBS_MAX == 4);

  fixture = read_file(
      FIXTURES_DIR "/agent-status-needs-you-codex-question.json", &fixture_len);
  if (fixture) {
    memset(&snapshot, 0, sizeof snapshot);
    check("Codex Needs You-fixturen parsar",
          tk_agent_status_parse(fixture, fixture_len, &snapshot));
    check("Codex pending binder provider och vy",
          snapshot.pending.present &&
          snapshot.pending.provider == TK_AGENT_PROVIDER_CODEX &&
          snapshot.pending.has_view_sha256 &&
          strcmp(snapshot.pending.view_sha256,
                 "9f4f6ec7a3519df610be969b66100fc0fefbe53a54cc59a82fb49dc70ba6e22a") == 0 &&
          strcmp(snapshot.pending.request_id,
                 "ABEiM0RVZneImaq7zN3u_w") == 0);
    free(fixture);
  }

  fixture = read_file(
      FIXTURES_DIR "/agent-status-needs-you-codex-approval.json", &fixture_len);
  if (fixture) {
    memset(&snapshot, 0, sizeof snapshot);
    check("Codex approval-fixturen parsar",
          tk_agent_status_parse(fixture, fixture_len, &snapshot) &&
          snapshot.pending.present &&
          snapshot.pending.kind == TK_PENDING_APPROVAL &&
          snapshot.pending.provider == TK_AGENT_PROVIDER_CODEX &&
          snapshot.pending.has_view_sha256);
    free(fixture);
  }

  /* "Needs You": pending är FRIVILLIG och tolkas mjukt. Ett trasigt
   * pending-objekt får aldrig ta agentlistan med sig — det är hela
   * skillnaden mot resten av den här parsern. */
#define QUESTION_PENDING \
  "{\"request_id\":\"6750af25a1f5ab4161fc7698c3f84d60\"," \
  "\"kind\":\"question\",\"project\":\"vibepulse\"," \
  "\"expires_in_ms\":118000,\"hold_ms\":144000," \
  "\"options_total\":2,\"marked\":true," \
  "\"prompt\":\"Which auth approach?\",\"title\":\"New auth layer\"," \
  "\"subtitle\":\"Cleaner architecture\",\"can_approve\":true}"
#define WITH_PENDING(PENDING) \
  "{\"v\":2,\"seq\":7,\"agents\":{" ONE_CLAUDE(WORKING_JOB) "," \
  EMPTY_CODEX "},\"pending\":" PENDING "}"

  memset(&snapshot, 0, sizeof snapshot);
  check("hel fråga läses in",
        PARSE(WITH_PENDING(QUESTION_PENDING), &snapshot) &&
        snapshot.pending.present &&
        snapshot.pending.provider == TK_AGENT_PROVIDER_CLAUDE &&
        !snapshot.pending.has_view_sha256 &&
        snapshot.pending.kind == TK_PENDING_QUESTION &&
        snapshot.pending.can_approve && snapshot.pending.marked &&
        snapshot.pending.options_total == 2 &&
        snapshot.pending.expires_in_ms == 118000 &&
        snapshot.pending.hold_ms == 144000 &&
        strcmp(snapshot.pending.request_id,
               "6750af25a1f5ab4161fc7698c3f84d60") == 0 &&
        strcmp(snapshot.pending.title, "New auth layer") == 0 &&
        strcmp(snapshot.pending.subtitle, "Cleaner architecture") == 0 &&
        strcmp(snapshot.pending.prompt, "Which auth approach?") == 0 &&
        strcmp(snapshot.pending.project, "vibepulse") == 0);
  check("agentlistan finns kvar bredvid en pending",
        snapshot.claude.job_count == 1 && snapshot.seq == 7);

  memset(&snapshot, 0, sizeof snapshot);
  check("payload utan pending ger present=false",
        PARSE(PAYLOAD(WORKING_JOB), &snapshot) && !snapshot.pending.present &&
        snapshot.claude.job_count == 1);

  /* Var och en av de här raderna är en payload som INTE får släcka
   * agentlistan. Det är kontraktet: fel i pending ⇒ ingen interaktion,
   * aldrig ingen agentstatus. */
  static const char *const soft_failures[] = {
      "{\"kind\":\"question\",\"expires_in_ms\":1}",           /* utan id */
      "{\"request_id\":\"abc\",\"expires_in_ms\":1}",          /* utan kind */
      "{\"request_id\":\"abc\",\"kind\":\"question\"}",        /* utan tid */
      "{\"request_id\":\"abc\",\"kind\":\"nonsense\","
      "\"expires_in_ms\":1}",                                  /* okänd sort */
      "{\"request_id\":\"abc\",\"kind\":\"question\","
      "\"expires_in_ms\":\"snart\"}",                          /* fel typ */
      "{\"provider\":\"future\",\"request_id\":\"abc\","
      "\"kind\":\"question\",\"expires_in_ms\":1}",        /* okänd provider */
      "{\"provider\":\"codex\",\"request_id\":\"abc\","
      "\"view_sha256\":\"ABCDEF\",\"kind\":\"question\","
      "\"expires_in_ms\":1}",                                  /* trasig digest */
      "{\"provider\":\"codex\",\"request_id\":\"abc\","
      "\"kind\":\"question\",\"expires_in_ms\":1}",        /* Codex utan digest */
      "{\"provider\":\"codex\",\"request_id\":\"abc|claude\","
      "\"view_sha256\":\"9f4f6ec7a3519df610be969b66100fc0fefbe53a54cc59a82fb49dc70ba6e22a\","
      "\"kind\":\"question\",\"expires_in_ms\":1}",        /* osäkert id */
      "\"inte ett objekt\"",
      "null",
      "[]",
      "{}",
  };
  for (size_t i = 0; i < sizeof soft_failures / sizeof soft_failures[0]; i++) {
    char payload[1024];
    snprintf(payload, sizeof payload,
             "{\"v\":2,\"seq\":7,\"agents\":{" ONE_CLAUDE(WORKING_JOB) ","
             EMPTY_CODEX "},\"pending\":%s}", soft_failures[i]);
    memset(&snapshot, 0, sizeof snapshot);
    bool parsed = tk_agent_status_parse(payload, strlen(payload), &snapshot);
    check("trasig pending tar aldrig agentlistan med sig",
          parsed && !snapshot.pending.present &&
          snapshot.claude.job_count == 1);
  }

  memset(&snapshot, 0, sizeof snapshot);
  check("saknad provider är legacy Claude",
        PARSE(WITH_PENDING(QUESTION_PENDING), &snapshot) &&
        snapshot.pending.present &&
        snapshot.pending.provider == TK_AGENT_PROVIDER_CLAUDE &&
        !snapshot.pending.has_view_sha256);

  memset(&snapshot, 0, sizeof snapshot);
  check("okända fält inuti pending bryter inte bygget",
        PARSE(WITH_PENDING("{\"request_id\":\"abc\",\"kind\":\"approval\","
                           "\"expires_in_ms\":5000,\"tool\":\"Bash\","
                           "\"title\":\"npm test\",\"can_approve\":true,"
                           "\"something_new\":42}"), &snapshot) &&
        snapshot.pending.present &&
        snapshot.pending.kind == TK_PENDING_APPROVAL &&
        snapshot.pending.can_approve &&
        strcmp(snapshot.pending.tool, "Bash") == 0);

  memset(&snapshot, 0, sizeof snapshot);
  check("utan titel går det aldrig att godkänna",
        PARSE(WITH_PENDING("{\"request_id\":\"abc\",\"kind\":\"approval\","
                           "\"expires_in_ms\":5000,\"can_approve\":true}"),
              &snapshot) &&
        snapshot.pending.present && !snapshot.pending.can_approve &&
        !snapshot.pending.has_title);

  memset(&snapshot, 0, sizeof snapshot);
  check("integritetsläget ger något att gå till, inget att godkänna",
        PARSE(WITH_PENDING("{\"request_id\":\"abc\",\"kind\":\"question\","
                           "\"expires_in_ms\":5000,\"project\":\"vibepulse\","
                           "\"can_approve\":false,\"options_total\":2}"),
              &snapshot) &&
        snapshot.pending.present && !snapshot.pending.can_approve &&
        !snapshot.pending.has_prompt && !snapshot.pending.has_title &&
        strcmp(snapshot.pending.project, "vibepulse") == 0);

  memset(&snapshot, 0, sizeof snapshot);
  check("för lång text kastas hellre än trunkeras här",
        PARSE(WITH_PENDING("{\"request_id\":\"abc\",\"kind\":\"question\","
                           "\"expires_in_ms\":5000,\"can_approve\":true,"
                           "\"title\":\"" \
  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  "aaaaaaaaaaaaaaaaaaaa\"}"), &snapshot) &&
        snapshot.pending.present && !snapshot.pending.has_title &&
        !snapshot.pending.can_approve);

  memset(&snapshot, 0, sizeof snapshot);
  check("kontrolltecken i titeln avvisas",
        PARSE(WITH_PENDING("{\"request_id\":\"abc\",\"kind\":\"question\","
                           "\"expires_in_ms\":5000,\"can_approve\":true,"
                           "\"title\":\"npm\\ttest\"}"), &snapshot) &&
        snapshot.pending.present && !snapshot.pending.has_title &&
        !snapshot.pending.can_approve);

  if (failures == 0) {
    printf("OK: alla agentstatus-v2-tester gröna\n");
    return 0;
  }
  printf("%d test föll\n", failures);
  return 1;
}
