# Product Pivot Current-State Audit

Date: 2026-07-26

Target repo commit inspected:
`ad8689fa25b89f77122c4cec7c7a6b9da3f500cf`

Playbook commit used:
`5583eca96c4d2d480b5574ed78bea63e0b07ebf0`

W29 run inspected:
`data/output/weekly_intelligence_runs/tra-weekly-2026-W29-20260720T050229508302Z-978f44004e97/`

Preferred `/mnt/data` copies were unavailable in this environment; the audit
uses the local run directory.

## Current Product Diagnosis

The repository contains extensive IRX infrastructure and formal report
contracts, but the operator still does not receive a useful product. The system
is optimized around generating weekly artifacts, while the real need is
source-grounded recall and application over the Telegram corpus.

## Verified Code Behavior

- `src/db/schema.sql` defines canonical `raw_posts`, normalized `posts`, and
  persistent `posts_fts` with insert/update/delete triggers.
- Read-only SQLite inspection found 3,477 rows in each of `raw_posts`, `posts`,
  and `posts_fts`.
- `src/assistant/pi_prompts.py` instructs PI Assistant to answer only from
  curated intelligence tools and not use raw Telegram firehose retrieval.
- `src/assistant/semantic_retrieval.py` implements request-local FTS over
  curated `IntelligenceRetrievalItem` objects and explicitly reports raw
  Telegram status as disabled.
- `src/assistant/pi_tools.py` exposes curated/report tools such as
  `search_intelligence_items`, `search_idea_threads`, `list_marked_posts`, and
  status helpers, not a full archive search tool.
- `src/output/weekly_intelligence_orchestrator.py` imports the V1
  `build_weekly_intelligence_brief_artifact` and
  `build_knowledge_atlas_artifact` builders for the delivered run stages.
- V2 Brief and Atlas code exists separately in
  `src/output/weekly_intelligence_brief_v2.py` and
  `src/output/knowledge_atlas_report_v2.py`.
- `src/output/reaction_personalization.py` requires atom/thread lineage for
  reaction effects; reacted posts without atoms become unconsumed by the
  report personalization path.
- `src/output/learning_layer.py` defines `read` as a stage and currently
  produces `read` counts from source-backed objectives, even though the source
  URL does not prove the operator read the material.

## Verified Artifact Behavior

W29 manifest:

- `schema_version`: `weekly_run_manifest.v1`
- `run_status`: `partial`
- `reporting_week`: `2026-W29`
- `reaction_sync`: succeeded
- `radar`: failed
- warning: required MVP Radar failed or did not match the run and period

W29 delivered Brief:

- `schema_version`: `split_ai_report.v1`
- `artifact_type`: `weekly_intelligence_brief`
- `contract_version`: `tra-intelligence-contract.v1`
- `source_atom_count`: 48
- `thread_count`: 24
- `canonical_thread_count`: 0
- `raw_compatibility_thread_count`: 24
- actions are repetitive "Verify and apply" fallbacks
- Radar failure is shown as package-level partial status

W29 delivered Atlas:

- `schema_version`: `split_ai_report.v1`
- `artifact_type`: `knowledge_atlas`
- `contract_version`: `tra-intelligence-contract.v1`
- `source_atom_count`: 48
- `thread_count`: 24
- `canonical_thread_count`: 0
- large audit/table-style surface remains prominent

Reaction snapshot:

- 236 candidate posts checked;
- 7 observed personal posts;
- coverage complete and visibility verified;
- all 7 reacted posts existed in canonical `posts`, had `posts_fts` rows, and
  had feedback rows;
- JSON scan found 0 Knowledge Atom links for all 7 reacted post IDs.

Reaction receipts in both Brief and Atlas:

- `personal_reaction_events_detected`: 7
- `unique_reacted_posts`: 7
- `posts_resolved`: 7
- `eligible_period_posts`: 7
- `unique_atoms_linked`: 0
- `unique_compatibility_threads_linked`: 0
- `unique_canonical_threads_linked`: 0
- `selected_items_linked`: 0
- `selected_signals_influenced`: 0
- `unconsumed_reaction_events`: 7
- status: `no_eligible_reactions`
- reason shown in HTML: posts do not yet have Knowledge Atoms

Project/Learning projection:

- no confirmed project implications;
- no weak watches;
- no source-backed tiny PR ideas;
- learning stage counts mark 8 items as `read`;
- source policy says passive reading is not mastery, but the state name still
  conflates source exposure with reading.

V2 previews:

- no W29 V2 Brief/Atlas files were found under `data/output` in this checkout.

## Documentation Claims

- `docs/IMPLEMENTATION_CONTRACT.md` v3.0 says output remains a weekly
  decision-support artifact and memory must not become a separate product.
- `docs/architecture.md` says the system produces weekly decision-support
  artifacts and is not a general memory platform.
- `docs/curated_semantic_retrieval.md` says PI Assistant keeps raw Telegram
  firehose posts out of assistant retrieval.
- `docs/hermes_pi_assistant_roadmap.md` rejects raw archive RAG and broad
  vector RAG as current scope.

These claims conflict with the new north star and are superseded by the
proposed ADR only after human approval.

## Verified Problems

1. Delivered W29 reports use the V1 intelligence contract and V1 reader
   surfaces despite V2 implementation existing elsewhere.
2. Seven personal reactions were detected, but none linked to atoms, topics, or
   ranking effects.
3. Knowledge Atoms are effectively a gate to report/assistant intelligence
   visibility.
4. PI Assistant retrieval intentionally excludes the raw Telegram archive.
5. Weekly Brief actions remain generic and push source verification back to the
   user.
6. Knowledge Atlas remains an exposed audit dump rather than a useful knowledge
   system.
7. Current Idea Threads show entity/version fragmentation; W29 has 24 raw
   compatibility threads and 0 canonical threads.
8. Project Intelligence produced no useful project-specific decisions for W29.
9. Radar failure contaminated the whole W29 release as a partial package.
10. Learning state conflates source-backed exposure with reading.
11. Existing architecture/contract docs reject broad searchable memory.
12. Infrastructure sophistication did not translate into operator value.

## Assumptions

- The private operator wants a conversational memory product over retained
  Telegram posts more than a richer weekly report.
- The existing SQLite archive can support the first FTS baseline without a new
  datastore.
- Human-approved gold queries can be created without committing private post
  text.
- The current W29 run is representative enough to justify a pivot proposal, not
  enough to prove final metrics.

## Live Behavior Not Yet Verified

- Current deployed systemd timer status.
- Current Telegram reaction sync against live channels after W29.
- Current assistant behavior in a real Telegram chat.
- Full test suite health after the documentation retrofit until
  `tools/verify_project.py` is run.
- Retrieval quality over full archive FTS for the proposed PRM workflows.

## User-Reported Dissatisfaction

The operator reports that the product still does not provide useful value
despite extensive IRX implementation. The reported failure mode is accepted as
product input and is now backed by the W29 artifact audit above.
