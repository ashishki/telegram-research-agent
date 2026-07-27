# Tool Evaluation Plan

Status: draft; PRM-4 archive search tool vertical slice recorded; PRM-9 routing and trace evidence recorded
Last updated: 2026-07-26

## Tool Classes

Read-only tools:

- `search_telegram_archive`: retained Telegram archive search through
  persistent SQLite FTS, bounded snippets, source links, and PRM-2 document
  identity;
- search curated knowledge;
- list reactions;
- get topic/project/saved context;
- get recent changes;
- get Radar status;
- request external verification.

Confirmation-gated proposal tools:

- propose Knowledge Note;
- propose Watch Topic;
- propose project link;
- propose action;
- propose experiment;
- propose feedback.

## Evaluation Checks

- tool schema rejects unexpected fields;
- read-only tools do not mutate SQLite or files;
- proposal tools do not write until confirmation;
- trace records tool name, arguments class, latency, result count, evidence
  status, and termination reason;
- unsafe/mutation tool names remain blocked;
- external verification is labelled separately from Telegram evidence.

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
| Read-only minimum | `get_current_week_label`, `get_weekly_summary`, `get_artifact_status`, `search_intelligence_items`, `search_telegram_archive`, `search_idea_threads`, `get_idea_thread`, `get_project_actions`, `get_mvp_radar_status`, `get_feedback_summary`, `list_marked_posts`, `get_strategy_reviewer_notes`, `request_external_verification` |
| Confirmation-gated proposals | `propose_knowledge_note`, `propose_watch_topic`, `propose_project_link`, `propose_action`, `propose_experiment`, `propose_feedback` |
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

## Stop-Ship Cases

- automatic profile/config/project mutation;
- assistant runs code edits or Codex;
- raw corpus text in ordinary logs;
- external skill reads secrets without trust approval;
- no-answer query produces unsupported claim.
