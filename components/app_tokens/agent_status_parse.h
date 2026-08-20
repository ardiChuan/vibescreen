#ifndef AGENT_STATUS_PARSE_H
#define AGENT_STATUS_PARSE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "agent_status.h"

bool tk_agent_status_parse(const char *json, size_t len,
                           tk_agent_snapshot *out);

/* Parse only the authenticated stable public view carried by the encrypted
 * interaction relay. This deliberately does not impersonate or apply a full
 * agent-status response. The caller supplies the already bounded remaining
 * lifetime and authenticated lowercase SHA-256. */
bool tk_agent_status_parse_relay_view(
    const uint8_t *view, size_t view_len, uint32_t expires_in_ms,
    const char view_sha256[TK_PENDING_VIEW_SHA256_CAP],
    tk_pending_interaction *out);

#endif
