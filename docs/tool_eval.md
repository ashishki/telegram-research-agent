# Tool Evaluation Plan

Status: draft; PRM-4 archive search tool vertical slice recorded; PRM-9 routing and trace evidence recorded; PRM-11 external verification requirement path recorded; PRM-12 confirmation-gated save/watch flow recorded; PRM-14 project context support recorded
Last updated: 2026-07-28

## Tool Classes

Read-only tools:

- `search_telegram_archive`: retained Telegram archive search through
  persistent SQLite FTS, bounded snippets, source links, and PRM-2 document
  identity;
- search curated knowledge;
- list reactions;
- get topic/project/saved context;
- analyze project context;
- get recent changes;
- get Radar status;
- request external verification.

Confirmation-gated proposal tools:

- propose Knowledge Note;
- propose Watch Topic;
- propose project link;
- propose decision;
- propose action;
- propose experiment;
- propose feedback.

Confirmation-gated write tools:

- `confirm_save_proposal`: persist an approved proposal only when the exact
  proposal object and confirmation token are supplied.

## Evaluation Checks

- tool schema rejects unexpected fields;
- read-only tools do not mutate SQLite or files;
- proposal tools do not write until confirmation;
- confirmed writes append events instead of updating or deleting prior events;
- trace records tool name, arguments class, latency, result count, evidence
  status, and termination reason;
- unsafe/mutation tool names remain blocked;
- external verification is labelled separately from Telegram evidence.

## PRM-UX-7 Telegram Post-Answer Actions

Research answers can expose a bounded PRM-only callback namespace for Knowledge
Note, Watch Topic, project/action/experiment when a project is present, and
operator feedback. Callback data contains only a short opaque answer-context ID
and action code. Selecting an action creates a volatile proposal and asks for a
second explicit confirmation; it does not write. Only the confirmation callback
uses the existing `confirm_save_proposal` path, which appends an event and
returns its `memory_id` and `event_id` for retrieval.

Fixture checks cover bounded markup, proposal-before-write, confirmed append-only
receipt, and feedback proposals that do not alter profile/project/provider
configuration or external systems. Legacy callback namespaces remain blocked in
the PRM runtime.

## PRM-4 Tool Evidence

Implementation:

- Tool catalog: `assistant.pi_tools.build_pi_tool_catalog`.
- Facade method: `PersonalIntelligenceFacade.search_telegram_archive`.
- Search backend: `db.archive_search.search_telegram_archive`.
- Tool schema is read-only and closed at the top level and filter object level
  with `additionalProperties: false`.
- Tool accepts only `query`, `filters`, and `limit`; it has no write,
  confirmation, SQL execution, DB path, code, config, profile, or project
  mutation fields.

Expected statuses:

| Case | Status |
| --- | --- |
| Archive tables unavailable | `missing` |
| Invalid query/search error | `invalid` |
| Matching source evidence | `ok` |
| No retained archive evidence | `insufficient_evidence` |

Verified fixture behavior:

- exact archive query returns a Telegram `source_url` and stable
  `archive_document_id` without requiring Knowledge Atoms;
- no-answer archive query returns `insufficient_evidence`, no items, and no
  fabricated `source_refs`;
- assistant chat can route a planned read-only `search_telegram_archive` call
  and include the source link in collected evidence;
- assistant no-answer fallback does not invent a Telegram citation.

Verification commands:

```bash
python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py tests/test_archive_search.py -q
```

Result:

```text
25 passed in 2.85s
```

## PRM-9 Tool And Router Evidence

Implementation:

- Tool catalog metadata now includes `read_only`, `requires_confirmation`, and
  `proposal_only`.
- Minimum read-only catalog is enforced by
  `assistant.pi_tools.validate_pi_tool_catalog`.
- Confirmation-gated proposal tools return `needs_confirmation` and
  `persisted=false`; no automatic mutation tools are present.
- `assistant.pi_chat.route_pi_intent` provides deterministic routes for exact
  search, concept search, cases, comparison, freshness/news, project
  application, reaction recall, no-answer probes, artifact status, Radar status,
  Strategy notes, and external verification requests.
- Assistant responses include `pi_assistant_trace.v1` with selected tool,
  bounded arguments, result count, evidence status, termination reason, and
  privacy boundary.

Required tool groups:

| Group | Tools |
| --- | --- |
| Read-only minimum | `get_current_week_label`, `get_weekly_summary`, `get_artifact_status`, `search_intelligence_items`, `search_telegram_archive`, `search_idea_threads`, `get_idea_thread`, `get_project_actions`, `analyze_project_context`, `get_mvp_radar_status`, `get_feedback_summary`, `list_marked_posts`, `get_strategy_reviewer_notes`, `request_external_verification` |
| Confirmation-gated proposals | `propose_knowledge_note`, `propose_watch_topic`, `propose_project_link`, `propose_decision`, `propose_action`, `propose_experiment`, `propose_feedback` |
| Confirmation-gated writes | `confirm_save_proposal` |
| Forbidden automatic mutation | `edit_code`, `run_codex`, `edit_config`, `mutate_profile`, `mutate_projects`, `write_feedback`, `record_feedback`, `confirm_feedback`, `mutate_db`, `execute_sql` |

Trace privacy boundary:

```json
{
  "raw_telegram_text_egress": true,
  "raw_telegram_corpus_egress": false,
  "bounded_telegram_snippet_provider_egress": true,
  "external_skill_used": false,
  "write_performed": false,
  "bounded_read_only_tools": true
}
```

`raw_telegram_text_egress=true` is limited to bounded cited snippets passed to
the answer-generation provider. Broad raw corpus egress remains forbidden and
is represented separately as `raw_telegram_corpus_egress=false`.

Verification command:

```bash
python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py tests/test_archive_search.py tests/test_archive_documents.py -q
```

Result:

```text
36 passed in 2.34s
python3 -m pytest tests/ -q
1 failed, 995 passed, 281 subtests passed in 241.48s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

## PRM-11 External Verification Evidence

Implementation:

- High-stakes or unstable questions now route deterministically through
  `request_external_verification`, so LLM planning cannot skip the requirement.
- Covered high-stakes routing categories are `pricing`, `legal`, `medical`,
  `financial`, `career_market`, and `visa`; freshness/news/current questions
  also require verification.
- The local `request_external_verification` tool returns a requirement DTO only.
  It does not browse, call external skills, automatically collect Telegram
  archive snippets, persist research notes, mutate profile/project state, or
  store chat transcript memory.
- Verification responses separate `telegram_evidence`,
  `external_evidence(status=not_run_unapproved)`, `unknowns`, `persistence`,
  and `privacy_boundary`.
- The grounded answer contract now exposes `evidence_sections` with separate
  `archive_evidence`, `external_evidence`, and `unknowns` sections.
- Tool catalog validation is an explicit allowlist. It rejects unapproved
  external-skill tool names such as `web_search` and unknown tool names before
  handler execution; `APPROVED_EXTERNAL_SKILL_TOOL_NAMES` is empty until a human
  approval and trust record exist.

Verification command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
python3 tools/test_tiers.py focused-prm
python3 tools/test_tiers.py fast-contract
```

Result:

```text
39 passed, 6 subtests passed in 14.25s
65 passed, 6 subtests passed in 12.74s
118 passed, 6 subtests passed in 58.27s
```

## PRM-12 Confirmation-Gated Save/Watch Evidence

Implementation:

- Proposal tools now produce `pi_memory_proposal.v1` objects with
  `confirmation.token`; they remain `read_only=true`, `proposal_only=true`,
  `persisted=false`, and `write_performed=false`.
- `propose_decision` was added so Knowledge Notes, Watch Topics, project links,
  decisions, actions, experiments, and feedback all have explicit proposal
  tools.
- `confirm_save_proposal` is the only confirmation-gated write tool. It is
  `read_only=false`, `requires_confirmation=true`, and rejects calls without an
  explicit facade or valid confirmation token.
- Confirmed writes require the canonical `personal_memory_events` schema from
  migrations; the tool handler does not create tables lazily.
- Confirmed writes append rows to `personal_memory_events`; replay of the same
  proposal/token returns the existing event without appending a duplicate.
- Edit, delete, and rollback are modelled as new events, not destructive
  updates, and their target memory/event ids are validated before writing.
- Chat save requests draft proposals only. Session chat text and transcripts do
  not create durable memory rows unless the user supplies the exact proposal and
  confirmation token.
- Fixture tests use temporary SQLite databases only. No production database
  contents were modified.

Verification command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
python3 tools/test_tiers.py focused-prm
python3 tools/test_tiers.py fast-contract
```

Result:

```text
39 passed, 6 subtests passed in 14.25s
65 passed, 6 subtests passed in 12.74s
118 passed, 6 subtests passed in 58.27s
```

## PRM-14 Project Context Evidence

Implementation:

- `analyze_project_context` was added to the bounded PI tool catalog as a
  read-only tool.
- The tool loads active project descriptors from local descriptor files, runs
  bounded SQLite FTS archive retrieval and curated intelligence search, and
  returns `project_context_decision_support.v1`.
- The DTO labels each answer as `direct_implication`, `weak_watch`,
  `learning_relevance`, or `no_match`.
- Direct implications include archive/source refs, descriptor fields used, and
  read-only candidate next steps.
- Weak keyword-only and learning-only matches return watch/study guidance and no
  project action recommendation.
- `approve_mvp_build`, `approve_project_build`, `build_mvp`,
  `mutate_project_context`, `mutate_projects`, `edit_code`, and `run_codex`
  remain forbidden by the explicit allowlist.
- Project-context chat routes bypass LLM planning and use deterministic answer
  rendering from the DTO.

Verification command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_context.py tests/test_pi_tools.py tests/test_pi_chat.py -q
python3 tools/test_tiers.py focused-prm
python3 tools/test_tiers.py fast-contract
```

Result:

```text
47 passed, 6 subtests passed in 5.59s
78 passed, 6 subtests passed in 11.38s
131 passed, 6 subtests passed in 33.79s
```

## PRM-UX-9 Primary-Source Verification Boundary

`assistant.primary_source_verification` creates a plan only. It separates a
Telegram discovery signal, preferred official/GitHub source candidates,
independent confirmation, changed facts, unknowns, and the revised
recommendation. Without both an approved trust record and separately approved
bounded live fetch, it returns `verification_required_not_run`; no external
skill, HTTP request, cache write, provider call, or durable note is performed.

## Stop-Ship Cases

- automatic profile/config/project mutation;
- confirmed write without exact proposal and confirmation token;
- destructive edit/delete/rollback that mutates prior memory events;
- assistant runs code edits or Codex;
- raw corpus text in ordinary logs;
- external skill reads secrets without trust approval;
- no-answer query produces unsupported claim.
