# PRM Local UX Trial - 2026-08-11

Status: diagnostic evidence, not PRM-19 dogfood
Scope: local CLI usability review after PRM-28 no-vector RAG acceptance

## Boundary

This trial simulated operator questions against local CLI surfaces only. It did
not start PRM-19, Telegram services, live Telegram ingestion, reaction sync,
live web research, provider egress, embeddings/vector backend, migrations,
production database writes, release claims, or compatibility archive/delete/move
work.

No raw Telegram post bodies or generated private reports are copied into this
receipt.

## Simulated Questions

The local trial covered:

- archive synthesis question about AI transformation in companies;
- project/eval question about why vector retrieval is not required now;
- current-fact/no-answer question about a live stock price;
- project-action question about what to do next in this repository;
- shorter `memory ask` checks for no-answer and RAG/vector questions.

Representative commands:

```text
PYTHONPATH=src python3 src/main.py memory research --limit 4 "<question>"
PYTHONPATH=src python3 src/main.py memory ask --limit 4 "<question>"
```

## Observed Metrics

| Surface | Cases | Output size | Visual notes |
| --- | ---: | --- | --- |
| `memory research` | 4 | 4.4k-5.6k chars, 57-66 lines | 12-15 lines over 140 chars per answer; many English static labels |
| `memory ask` | 2 | 0.6k-3.1k chars, 11-27 lines | shorter and clearer, but can expose absolute local artifact paths |

Post-polish spot-check on three representative `memory research --limit 4`
queries:

| Surface | Cases | Output size | Visual notes |
| --- | ---: | --- | --- |
| `memory research` compact default | 3 | 1.56k-1.72k chars, 29-30 lines | 3-5 lines over 140 chars; `Citation-Safe Context Pack` hidden unless `--debug`; current-fact case had no drafts |

Shared safety observations:

- local mode kept `model_calls=0`;
- provider egress, raw Telegram corpus egress, live linked-source fetch,
  external skill use, durable writes, embeddings, and vector backend stayed
  false;
- source links and privacy lines were visible in the CLI output.

## What Works

- The RAG retrieval/eval layer is fast and citation-oriented enough for local
  archive discovery.
- The answer gate is effective in the short `memory ask` current-fact path:
  current/live facts are refused without external verification instead of being
  presented as current truth.
- The `memory research` output is auditable: it shows archive evidence,
  linked-source absence, context-pack state, unknowns, draft proposal state,
  planner limits, and privacy flags.

## UX And Product Gaps

1. `memory research` is not answer-first enough.
   The Direct Answer often reads like a concatenated retrieved snippet plus
   routing metadata, not like a concise user-facing synthesis.

2. Current-fact/freshness questions are too easy to misread in
   `memory research`.
   Even when `external_verification_required=true`, the answer can lead with
   related archive evidence and "found grounded evidence" language. For current
   facts, the first line should say that the current fact cannot be verified
   locally.

3. Russian UX is mixed with English product labels.
   Headings such as `Direct Answer`, `Approach Comparison`, `Project Fit`,
   `Citation-Safe Context Pack`, and `Draft Proposals` are clear to engineers
   but not pleasant for a Russian-language operator flow.

4. The context-pack section is useful for debugging but noisy for daily use.
   It repeats archive snippets, includes low-value curated memory rows, and
   makes the answer feel like an audit receipt rather than a research assistant.

5. Curated/project memory relevance needs tightening.
   Some simulated questions pulled curated memory about unrelated model/news
   topics, which dilutes trust in the answer.

6. Project-action questions do not yet route strongly enough to repo/task/eval
   evidence.
   A question about what to do next in this repository was answered primarily
   from Telegram archive evidence, not from `docs/tasks.md`, release receipts,
   or current gate state.

7. `memory ask` can expose absolute local artifact paths.
   For operator readability, sources should prefer relative repo paths,
   friendly labels, or Telegram/source IDs rather than `/srv/...` paths.

8. The terminal startup banner appears in direct terminal usage.
   It is useful operational metadata, but it competes with the answer in a
   user-facing reading flow.

## Verdict

The accepted no-vector RAG path is technically usable for local archive
discovery and gated current-fact refusal, but the default user-facing experience
is not yet "pleasant" or fully comfortable for daily use.

Safe UX polish implemented after this trial:

1. Added a compact default reading view for `memory research`.
2. Moved context-pack/provenance detail behind `memory research --debug`.
3. Localized the default Russian-language headings and common next-step labels.
4. Made freshness/current-fact limitations the first line for current-fact
   questions.
5. Redacted/relativized local repository paths in `memory ask` rendered source
   refs.
6. Added a narrow repo-context cue for explicit `telegram-research-agent`
   project questions so repo docs and gate receipts are shown before Telegram
   archive background.
7. Blocked draft proposals for current-fact freshness-boundary answers.
8. Added local-only Telegram `/brief` editor briefs and volatile per-chat
   `/research` follow-up context for short replies such as "а почему?".
9. Added deterministic AI-transformation query hints for implementation
   success, ROI/productivity, failure/no-growth, and hiring/layoff angles.
10. Corrected the answer gate so archive-scoped recent-post questions can be
    answered from local archive context while current-price/current-stock
    questions still require external verification.

Remaining known UX gaps:

- deterministic synthesis is still shallower than an LLM-backed editor;
- curated memory relevance/deduplication still needs deeper scoring;
- multi-turn context is volatile/in-process only and is not durable product
  memory;
- the operational startup banner is emitted on stderr in direct terminal use;
- live/current linked-source verification remains gated and was not run.

## Validation

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_rag_context_pack.py tests/test_handlers.py tests/test_callbacks.py tests/test_product_rag_eval.py tests/test_archive_retrieval_eval.py -q
86 passed in 28.34s
```

```text
python3 tools/test_tiers.py focused-prm
139 passed in 24.78s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_rag_context_pack.py tests/test_handlers.py tests/test_callbacks.py -q
71 passed in 24.79s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_local_memory_ask.py tests/test_cli.py -q
35 passed in 4.41s
```

```text
python3 tools/test_tiers.py focused-prm
134 passed in 22.88s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```
