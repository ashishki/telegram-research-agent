# PRM Block Review Corrective Log - 2026-07-26

Status: active corrective review evidence
Reviewer: Codex main agent
Authority: docs/REVIEW_POLICY.md, docs/tasks.md, docs/PRIVACY_THREAT_MODEL.md

## Context

This review was created after a process miss: implementation continued across
PRM block review boundaries without first recording the block review evidence
required by `docs/REVIEW_POLICY.md`.

Child review agents are optional under the current policy. Tool discovery for a
multi-agent read-only reviewer returned no callable tools in this environment,
so this is a main-agent corrective review and must not be represented as an
independent external review.

No further PRM implementation should proceed from this state until this
corrective review is committed and pushed with the implementation evidence.

## Stop-Ship Boundary Check

Reviewed stop-ship boundaries:

- Raw Telegram text egress: not introduced. Reports and eval JSON omit queries,
  snippets, source URLs, and raw Telegram text where the artifact is intended as
  sanitized evidence.
- External skill approval: not introduced.
- Unsafe write or confirmation bypass: not introduced. Proposal tools return
  `needs_confirmation` and `persisted=false`.
- Production database migration: not introduced.
- Vector backend adoption: not introduced. PRM-8 remains blocked and
  `ADR-002` is `proposed_not_accepted`.
- Dogfood start or release claim: not introduced.
- Deletion/archive/move of compatibility files: not introduced.

## Findings

REV-1 - Process gate violation - P1 - fixed by corrective evidence.

PRM-2, PRM-4, PRM-6, and the PRM-7/PRM-8 boundary were crossed without a
recorded block deep review. The implementation artifacts were reviewed in this
corrective pass, but the ordering violation remains part of the audit history.

REV-2 - PRM-7 latency metric mixed gold and candidate rows - P2 - fixed.

`src/db/archive_retrieval_eval.py` aggregated gold `latency_ms_p95` from all
cases, including unapproved candidates. This did not change the current vector
gate because there are zero human-approved gold rows, but it violated the
gold/candidate separation contract for future mixed datasets. The evaluator now
keeps separate gold and candidate latency arrays. The sanitized baseline report
was regenerated.

## Block Results

| Block | Review disposition | Notes |
| --- | --- | --- |
| PRM-1 through PRM-2 | pass with process repair | Read-only corpus inventory and archive document identity are bounded to local SQLite inspection and deterministic mapping. No raw text was copied into generated public evidence. |
| PRM-3 through PRM-4 | pass with process repair | SQLite FTS archive search and assistant vertical slice are read-only. Runtime snippets/source URLs are bounded tool outputs, not committed private reports. |
| PRM-5 through PRM-6 | pass with process repair | Reaction fast lane and selective enrichment keep search availability separate from extraction success. Receipts exclude raw text and provider payloads. Selective enrichment uses an injected extractor and does not call a provider. |
| PRM-7 through PRM-8 | pass after fix; PRM-8 blocked | PRM-7 evaluator separates candidate diagnostics from gold metrics. No vector backend or embeddings were adopted. PRM-8 remains blocked until human-approved gold labels and accepted ADR evidence exist. |
| PRM-9 through PRM-12 | open interim status | PRM-9 and PRM-10 have implementation evidence, but PRM-11 and PRM-12 are not started. This block review gate is not closed. |

## Verification Evidence

Focused corrective verification after REV-2:

```text
python3 -m pytest tests/test_archive_documents.py tests/test_archive_search.py tests/test_pi_tools.py tests/test_pi_chat.py tests/test_reaction_fast_lane.py tests/test_selective_enrichment.py tests/test_archive_retrieval_eval.py -q
46 passed in 1.81s
```

PRM-7 sanitized read-only SQLite evaluation rerun after REV-2:

```text
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/query_set_candidate.jsonl --limit 10 --json evals/retrieval/prm7_fts_baseline_report.json
archive_retrieval_eval: rows=50 gold=0 candidates=50 output=evals/retrieval/prm7_fts_baseline_report.json
```

Regenerated report summary:

```text
rows=50
gold=0
candidates=50
candidate_p95_latency_ms=59.988
candidate_duplicate_top10_rate=0.008
reacted_post_searchability=0.956522
gold_status=not_scored_no_human_approved_gold
vector_status=blocked_no_human_approved_gold
vector_backend_adopted=false
embeddings_run=false
privacy.raw_telegram_text_printed=false
privacy.snippets_included=false
privacy.source_urls_included=false
privacy.queries_included=false
```

Latest full-suite status after this corrective review:

```text
python3 -m pytest tests/ -q
1 failed, 996 passed, 281 subtests passed in 227.81s
```

Known failure only:

```text
tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

The project handoff already identifies this as date-sensitive live evidence
expiry on 2026-07-26, and it was explicitly excluded from this repair scope.

Final verification commands for this corrective commit set must still include:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
git diff --check
```

## Human Approvals Still Required

- Candidate retrieval queries are not gold evidence until the operator approves
  labels and expected citations.
- Vector backend adoption remains blocked.
- PRM-8 implementation remains blocked.
- PRM-9 through PRM-12 block review remains open until PRM-11 and PRM-12 are
  completed or explicitly deferred with operator approval.
- Human operator remains final completion authority.
