# D04 + D10 — coherent local design

Base `62a2909`; branch `codex/pa-daily-implementation-20261013`. This concrete
design does not grant exact human/role acceptance, access, paid calls or release.

Use existing RequestIntent, root, queues, ConversationStore and policy. Persist
owner/bot/default-thread focus and admission tickets as logical versioned records,
without changing existing DDL/checksums. Intake freezes the intended object and
generation; replay never reselects a target. Priority reply, explicit owner ref,
active focus, one recent eligible object; ambiguity/deletion fails closed. New
topic resets focus; document refs remain lookupable. Project/version and source
filters are request-scoped, never grants or a persistent preference inferred
from source text. Foreground completion promotes only its admission generation;
late/background results retain immutable output without stealing current focus.
Reply/old-result work keeps isolated context and no inherited confirmations.

Conversation mutations use a focus fence around short state operations, never
hold the focus lock during model I/O. Queued completion promotes atomically under
the existing lineage/job transaction. Focus refs/tickets depend on source/input/
result records; serving/egress rechecks current input/version/source permissions.
Topic/business routing remains D59/D60 and cannot collapse into default history.

Optional schema-bound planner proposes at most three registered read/compose/
preview steps. Deterministic controls and exact confirmation paths take priority.
No executor, grant, memory commit, schedule activation or model-derived public
query. Scope for intent.plan is distinct; private focus content is not included
in the planner packet. Explicit scoped model calls use D05 client/attempt ledger;
accepted/malformed/unknown planning attempts are durable and not retried. No
model/scope yields honest deterministic fallback; bad plans clarify/fail closed.
Synthetic fake planner and loopback inference prove wiring, not real understanding.

SourceBatch/EvidenceBundle carry selected resource/account/owner identity,
versions, publication/event/discovery times, checked_at, pagination/continuation,
completeness, known omitted counts and reasons. Legacy list/dict collectors remain
bounded/unknown. Archive window enumeration and source counts precede separate
bounded model selection; >48 inputs do not imply all selected/cited. Merge never
collapses account scopes; distinct received/candidate/selected/cited counts.
Adapt native archive/web/research/Brief hooks and Graph observations additively;
no private corpus copy, new account or retrieval/model permission.

Checks: new conversation/coverage tests, whole10–20-turn native sessions,
late completion/restart/new topic/old reply/ambiguity/malformed/injection and
revocation/unknown planning. Source cases cover >48, unavailable/empty/partial,
unknown dates, late sources, boundaries/conflicts and explicit resource identities.
One committed package review; narrow independent P0/P1 rechecks only. Synthetic
PG/SQLite/loopback, no .env/private target/paid/provider calls or Mini App.
