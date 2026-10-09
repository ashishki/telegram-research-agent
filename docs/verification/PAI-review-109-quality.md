# Actual109 structural ADVISORY — self-referential summary rejected

2026-10-09. Actual sources109 ata063833,599.733s,
usage42536/49013/91549, observed glm-5.3/requested max/observed effort unknown.
Original result/report/command/input/hash receipt PAI-review-continuation-109.json
remains unchanged. Four detailed P2 findings are retained, but summary is exactly
"See summary field." and supplies no actual conclusion. Like102's placeholder
and106's Incomplete-only summary, it is not consumed as a complete part or P1
closure.109 counts as consumed. No fabricated STOP, corrected provider text,
identity, usage or human approval is produced.

Local PAI-00 tooling response: reject known whole-field placeholder summaries,
fixes and limitations at parse_response, before report/generic record publication.
Normalize whitespace/case/trailing punctuation only; do not reject substantive
summaries explaining incomplete LIVE evidence or rewrite a reviewer's conclusion.
Provider schema descriptions and prompt now ask for scoped surfaces, P0/P1
conclusion and evidence limits. This is a necessary quality guard for actual
observed invalid reports; not a general semantic-quality guarantee or a resource
cap. Max/input/output/watchdog/provider/model/privacy source scope is unchanged.

Actual fake-provider execution proves one call, failure-only artifact, no report/
design record and retention of genuine reported identity/usage, without raw
response/sentinel leakage. Scoped185 tooling/bridge/plan/acceptance-guard tests
passed7.68s; pin/32 packets/69 IDs/ten scenarios/diff passed. Runtime source is
unchanged; prior87/163/21 cases are dated separately, not rerun as current full CI.
Critical sources changed: old93 is now stale. Independent tooling110 required
before any new design request/record consumption; no self-closure. Then sources111
P1 recheck and all fresh112..118 at one unchanged committed HEAD/design/audit if
clear. Ongoing necessary-review authority, one request each/no automatic retry
or fallback; all originals including108 manual transport-stall cancellation kept.

## Original actual report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: ADVISORY

{
  "verdict": "ADVISORY",
  "findings": [
    {
      "severity": "P2",
      "title": "PAI-18 under-wired: missing PAI-14 dependency and no complete-gate coverage of its declared outcome",
      "issue": "PAI-18's scope text wires calendar into replies, Brief and watch evidence, but its declared dependencies are only PAI-10 and PAI-16; PAI-14 (briefs and its source hooks) is not transitively reachable (PAI-10 -> 03/05/07/09 -> 04/08; PAI-16 -> 03/07), src/prm/briefs.py is not in PAI-18 allowed_files, and its acceptance argv (test_pai_schedule_runtime, test_assistant_calendar, test_assistant_contacts) contains no Brief case. PAI.requirements.json binds PAI-18 only to CONNECT-01/CONNECT-02 and omits it from BRIEF-06 and SC13.2-04, so PAI-26's 69-ID/10-scenario gate never exercises schedule-conflict, timezone or contact-disambiguation behavior. Reachable case: the registry permits ordering PAI-18 before PAI-14; the Brief sub-scope is then unimplementable without a file-boundary violation or is",
      "fix": "Add PAI-14 to PAI-18 dependencies (or remove Brief wiring from its scope text), and bind PAI-18 to BRIEF-06/SC13.2-04 or a dedicated requirement case that verifies conflict detection, timezone conversion and contact disambiguation through the real composition root."
    },
    {
      "severity": "P2",
      "title": "Connector derived-store/cursor repository and new scope-vocabulary ownership unassigned in phase E",
      "issue": "PAI.md assigns pa_connections.cursors/source_records to a Connector repository, and PAI-17 (delta checkpoints, derived store) and PAI-18 (paging/sync) need it, but neither card may write src/prm/storage/**; within this phase only PAI-16 and PAI-19 can, and PAI-19 depends on PAI-17/18. PAI-16's scope, rollback and acceptance cover only OAuth/token lifecycle: no cursor or source-record schema or test is bound anywhere. Likewise, new operation/scope vocabulary (contacts and calendar scopes, PAI-20's app-level action.reconcile read scope) is only editable in PAI-16 (src/prm/capabilities.py) while PAI-17/18/20 must enforce those scopes without touching it. Reachable case: the PAI-17 implementer needs a durable delta-cursor repository; if PAI-16 did not build it (nothing in PAI-16's scope binds它",
      "fix": "Explicitly assign pa_connections cursors/source_records repository construction plus its schema and acceptance tests to PAI-16 (or grant PAI-17/18 scoped storage access), and state in the registry where new scope/operation vocabulary is registered and tested."
    },
    {
      "severity": "P2",
      "title": "Concurrent same-connection source sync serialization and cursor CAS unspecified",
      "issue": "PAI-16 requires serialized same-connection refresh (required node test_same_connection_refresh_is_serialized_before_http), but PAI-17/18 specify no per-connection sync serialization, no unique in-flight sync job, and no cursor CAS/monotone watermark. Reachable case: a scheduled watch sync occurrence and an owner-triggered sync both run for one connection; interleaved delta pages can double-apply changes or regress the cursor to an older opaque delta token, with recovery degrading to the specified delta reset instead of preventing the race. Guards checked: job/occurrence uniqueness only prevents duplicate schedule-triggered jobs; no supplied guard covers concurrent cross-trigger syncs on one connection.",
      "fix": "Require per-connection sync serialization or a unique in-flight sync job per connection plus cursor CAS/watermark, and add a concurrent same-connection sync acceptance test to PAI-17/18."
    },
    {
      "severity": "P2",
      "title": "Connection-derived revocation/deletion behavior has no phase-E verification binding",
      "issue": "PAI-16's user-visible outcome includes revoking and deleting derived data, and PAI.md retention promises revocation hides related source/results, invalidates jobs/caches/reader links and queues derived deletion. However PAI-16's required nodes cover only credential at-rest/revoke/export exclusion, and SEC-04 and SC13.2-10 bind PAI-21/24/25/26 (memory/ops/migration): no required case in this phase exercises revoke-to-derived-invisibility, pending job/cache invalidation or deletion-queue behavior for mail/calendar/academic source_records. Reachable case: owner revokes the Graph connection; stale mail-derived brief facts and queued sync jobs remain servable because no phase-E test binds the invalidation path (CONNECT-02 binds provider documentation, not the propagation behavior).",
      "fix": "Add a required node to PAI-16/17 (or extend SEC-04/SC13.2-10 slice bindings to include PAI-16/17) exercising connection revocation hiding derived records, invalidating pending jobs/caches and queueing deletion with honest partial_deletion status."
    }
  ],
  "not_verified": [
    "Existence and content of all planned test files and required nodes (tests/test_pai_connections.py, test_pai_graph_mail.py, test_pai_schedule_runtime.py, tests/test_pai_academic_runtime.py, tests/test_pai_action_runtime.py and the named mail",
    "存在与内容未知，仅为计划义务。"
  ],
  "summary": "See summary field."
}
