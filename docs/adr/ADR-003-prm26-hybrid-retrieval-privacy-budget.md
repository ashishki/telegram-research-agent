# ADR-003: PRM-26 Hybrid Retrieval And Privacy Budget Gate

Status: accepted_no_vector_for_now
Date: 2026-08-11
Approval: operator-approval-2026-08-11-no-vector-prm28-path

## Context

PRM-24 produced a 50-row operator-approved generated seed gold set under
`operator-approval-2026-08-11-all-50-generated-gold` and a privacy-safe
SQLite FTS/query-planner baseline report:
`evals/retrieval/product_rag_fts_baseline_report.json`.

Current baseline metrics on that generated seed set:

| Metric | Value |
| --- | ---: |
| Gold rows | 50 |
| hit@10 | 1.0 |
| MRR | 1.0 |
| citation_precision | 1.0 |
| duplicate_top10_rate | 0.004 |
| latency_ms_p95 | 46.912 |
| no_answer_accuracy | 0.0 |
| stale_rejection | null |

PRM-25 has a citation-safe context-pack substrate that can carry bounded
archive, curated, linked-source, project, freshness, and unknown evidence
without provider egress, live fetching, embeddings, migrations, or writes.

## Decision

Do not adopt a vector backend in PRM-26. Proceed to the PRM-28 no-vector
answer-gate path over SQLite FTS/query planner and the citation-safe context
pack.

The current generated seed evidence does not show a source-recall or citation
precision failure that vector retrieval would clearly fix. The measured gaps
are:

- raw FTS returns related evidence for no-answer/control questions, so
  answer-level refusal and unsupported-claim gating must improve before product
  acceptance;
- stale/forbidden-document rejection is unmeasured because no stale labels were
  approved in the seed set;
- generated seed labels are useful for scaffolding, but they are not
  independent human-reviewed relevance evidence.

PRM-27 remains blocked. No embeddings were run, no vector database was created,
no production index was written, and no migration or provider call was made.

## Backend Comparison

| Candidate | Recall/fit | Precision/no-answer | Latency | Update complexity | Privacy | Cost | Backup/rollback | Current decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SQLite FTS + deterministic query planner | Recovers generated seed source labels at hit@10=1.0 | Does not solve no-answer by itself | p95 46.912 ms | Existing path | Local only | $0 | Existing SQLite backup; derived FTS rebuild | Keep as baseline |
| SQLite FTS + stricter answer/no-answer gate | Targets measured no-answer gap without new index | Directly addresses unsupported-claim refusals | Local; expected low overhead | Assistant/context-pack logic only | Local only | $0 for deterministic tests | Code rollback only | Preferred next non-vector path |
| SQLite FTS + linked-source freshness workflow | Targets freshness/stale gaps after approved fetch policy | Separates Telegram discovery from current-source claims | Depends on approved fetch/cache mode | Existing PRM-22/PRM-23 fixture path first | Live fetch/cache requires approval | $0 in fixtures; live budget TBD | Cache is derived; fallback to archive | Safe only in fixture mode now |
| Local embedding model + SQLite vector extension | May help future semantic misses if independent labels show them | Can add false positives without reranking/refusal controls | Unknown until benchmarked | Embedding lifecycle and native extension | Can remain local | Runtime/storage cost TBD | Derived index rebuild required | Not approved |
| Local embedding model + Chroma-like sidecar | May help semantic misses | Requires provenance and dedupe controls | Unknown; service overhead | New service lifecycle | Local if configured correctly | Runtime/storage cost TBD | Separate backup/restore | Not approved |
| Postgres/pgvector | May help semantic misses at larger scale | Requires answer gating anyway | Unknown; service/network overhead | New database/service/migration | Adds operational boundary | Hosting/storage cost TBD | Separate backup/restore | Not approved |
| External embeddings or vector service | May help semantic misses | Requires provider payload controls and reranking | Network-dependent | Provider integration and sync | Private corpus egress risk | Provider cost TBD | Provider export/restore dependency | Rejected unless explicitly approved later |

## Failure-To-Mechanism Map

| PRM-24 observation | Likely cause | Mechanism that can plausibly fix it | Vector needed now? |
| --- | --- | --- | --- |
| hit@10=1.0 and citation_precision=1.0 on generated source labels | Labels were generated from the local planner output | Independent human/holdout labels, not a new backend | No |
| no_answer_accuracy=0.0 | FTS returns related discussion for impossible/current-state claims | Answer-level evidence sufficiency classifier, explicit unsupported-claim refusal, PRM-28 no-answer acceptance tests | No |
| stale_rejection=null | No stale/forbidden labels approved | Add explicit stale/forbidden labels and external-verification cases | No |
| linked-source freshness questions require current facts | Telegram archive is discovery context, not current evidence | PRM-22/PRM-23 linked-source workflow with explicit live-fetch/cache approval | No vector by default |
| possible future semantic misses | FTS token matching can miss paraphrases | Local hybrid candidate only after independent labels show recall failures | Conditional |
| duplicate_top10_rate=0.004 | Duplicate crowding is low in current seed eval | Existing dedupe/provenance is sufficient for now | No |

## Privacy And Cost Budget

Current approved PRM-26 no-vector budget:

| Control | Value |
| --- | --- |
| Embedding provider | none approved |
| Embedding model | none approved |
| Vector backend | none approved; no-vector path accepted |
| Rows allowed for embedding | 0 |
| Tokens/chars allowed for embedding | 0 |
| Provider egress | false |
| Production index writes | false |
| Migrations | false |
| Durable vector/cache writes | false |
| Max model calls | 0 |
| Max provider cost | $0 |
| Logs/receipts | aggregate counts, metrics, IDs, and approval refs only; no raw Telegram text, snippets, prompts, completions, or provider payloads |

Any future vector experiment must record a new explicit approval reference,
backend/model choice, max rows, max tokens/chars, persistence boundary,
redaction/logging rules, rollback plan, and cost ceiling before execution.

## Rollback

Because PRM-26 creates no vector state, rollback is a code/docs revert.

If a future approved vector/hybrid implementation starts, it must:

1. Keep `raw_posts` and `posts` canonical and immutable for rollback.
2. Record vector schema/index version, embedding model/version, source row
   counts, and content-hash basis.
3. Write only derived index state.
4. Provide a feature flag or configuration path that disables vector retrieval
   and falls back to SQLite FTS.
5. Back up the SQLite database and any sidecar index before production writes.
6. Verify aggregate counts and eval metrics without printing raw Telegram text.

## Gate

PRM-27 must not start from this ADR. The accepted path is no-vector for now:
PRM-28 may implement answer-level sufficiency/no-answer/freshness gating over
SQLite FTS/query planner and the citation-safe context pack. A future vector
experiment requires a successor ADR with explicit backend/model, privacy, cost,
and rollback approval.
