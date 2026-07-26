# RAG Data Readiness

Status: draft; PRM-1 owns empirical completion

## Current Observations

Read-only SQLite inspection during retrofit:

| Table | Count |
| --- | ---: |
| `raw_posts` | 3,477 |
| `posts` | 3,477 |
| `posts_fts` | 3,477 |
| `knowledge_atoms` | 1,346 |
| `idea_threads` | 1,290 |
| `signal_feedback` | 23 |

This proves an archive and FTS table exist locally. It does not prove retrieval
quality or assistant access.

## PRM-1 Inventory Requirements

Measure:

- configured channels and enabled/disabled state;
- retained raw text availability;
- normalized content availability;
- Telegram URL coverage;
- channel/message/date coverage;
- language coverage;
- content hash coverage;
- duplicate/repost rate;
- empty or malformed posts;
- stale or missing source URLs;
- reaction coverage and unmatched reactions;
- private/public fixture boundary.

## Required Data Decisions

- canonical post body source;
- exclusion policy for non-text, empty, deleted, or inaccessible posts;
- duplicate/repost collapse policy;
- chunking threshold for long posts;
- retention and deletion rules;
- backup and reindex path;
- provider egress approval boundary for embeddings or LLM context.

## Gold Query Process

`evals/retrieval/query_set_candidate.jsonl` contains candidate queries only.

A query becomes gold only when the human operator supplies or approves:

- expected relevant post IDs or source URLs;
- freshness expectation;
- no-answer expectation when applicable;
- allowed distractors or known ambiguity;
- privacy/sanitization status.

No private raw post text should be committed as gold evidence.
