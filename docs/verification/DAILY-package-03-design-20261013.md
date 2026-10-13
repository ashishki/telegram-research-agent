# D05 + D06 — local package design

Base `980087f`; branch `codex/pa-daily-implementation-20261013`. This is concrete
implementation design, not exact human approval or governed design acceptance.

Extend ScopedModelClient and its existing durable reservations/logical attempt
fence. Extract Chat Completions protocol and bounded HTTP/SSE parsing; immutable
explicit capabilities choose token parameter, accepted returned model identities,
usage semantics and streaming. No prefix/automatic alias or provider fallback.
Old endpoints retain their compatible defaults. New configuration is validated
offline before startup. Own fixed User-Agent; stable explicit Go session/workload
selection, never impersonation. Go personal workload suitability remains unknown.

The same reserved call path handles sync and opted-in streams. Buffer final text;
partial events carry no tool/confirmation authority. Bound request/output/wire/
events and deadline; cancel or incomplete usage leaves unknown accounting and
no retry. Accepted usage records actual returned model, requested identity,
stop reason and subset semantics without double counting. Safe rejection status/
retry_after has no raw response/header/URL; no automatic retry. Keep source,
owner/provider/credential, revoke and attempt fences. No DDL/checksum changes.

Freeze first 20 synthetic tasks across Chat/Search/Brief/dialogue/Watch/Act,
with source snapshots, constraints, exact typed object bindings and forbidden
effects. Expandable manifest preserves 120-unit target (40/30/16/20/14), without
claiming missing units complete. Initial regression cases are dev evidence;
independent holdout/human usefulness remains open. Reject cross-split source and
scenario leakage. Run genuine native fixtures and record visible turns, bounded
typed results, versions, errors, actual latency and known/unknown cost. Public
export requires exact declared synthetic strings; arbitrary provider/private
payloads and secret canaries fail closed. Recordings are not provider runs.

Trace verifier binds input/source/manifest hashes, required case/turn/evidence,
typed expected status/object relations and actual effects. It cannot award PASS
for keywords or a caller-supplied success flag. Runner rejects missing, duplicate,
skipped, failed or changed cases, and distinguishes local mechanics from quality.
Existing datasets/acceptance guard remain intact. Review covers the entire
committed package once; P0/P1 fixes receive a narrow independent recheck only.

Checks: new daily protocol/manifest tests; affected chat/cost/session/strict
acceptance guard nodes; offline config/plan/pin/reference checks. Only loopback
HTTP and isolated synthetic PostgreSQL. No .env/key/private target/provider
calls, services, timers, production, external effects or Mini App.
