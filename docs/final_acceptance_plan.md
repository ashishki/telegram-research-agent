# Final Acceptance Plan

Status: proposed targets requiring human approval

## A. Data Readiness Targets

- At least 99% of retained text posts are indexable or have explicit
  exclusions.
- Required metadata coverage is at least 99%.
- Duplicate/repost policy is measurable.
- Every citation resolves to a Telegram source or explicit missing-source
  state.
- Private-data handling and retention are documented.

## B. Retrieval Dataset

Create 50 candidate queries:

- 8 exact known-item;
- 8 semantic topic;
- 8 case-study;
- 6 comparison;
- 6 freshness/news;
- 6 project/life application;
- 4 distractor;
- 4 no-answer.

Agent-drafted queries remain candidates until human-approved. No automatically
invented query may be labelled gold evidence without explicit operator
approval. PRM-24 records one such approved generated seed-label run:
`operator-approval-2026-08-11-all-50-generated-gold`.

## C. Retrieval Metrics

Draft targets:

- known-item hit@10 >= 0.85;
- MRR >= 0.65;
- citation precision >= 0.90;
- stale-document rejection >= 0.90 on freshness cases;
- no-answer accuracy >= 0.80;
- duplicate top-10 result rate <= 0.10;
- p95 local retrieval latency <= 1.5 seconds;
- 100% of detected reacted posts searchable after the same sync run.

PRM-24 generated seed baseline evidence passes source-label
hit/citation/latency thresholds, but raw retrieval no-answer accuracy is 0.0
and stale rejection is unmeasured. PRM-28 therefore adds a no-vector
answer-level gate: current generated seed answer-gate metrics pass no-answer
accuracy, external-verification boundary, current-claim rejection, and
answerable-source-label checks at 1.0. This is product RAG gate evidence, not
dogfood or release evidence.

## D. Generation Metrics

- faithfulness;
- completeness;
- relevance;
- citation correctness;
- no-answer correctness;
- unsupported-claim rate;
- human correction/rejection rate;
- answer usefulness;
- p95 end-to-end latency;
- cost per useful answer.

LLM judge output is advisory until calibrated against human labels.

## E. End-To-End Scenarios

1. Find a known reacted post.
2. Answer a semantic topic question over multiple months.
3. Find and compare several cases.
4. Apply archive evidence to one active project.
5. Answer a freshness/news question with clear date boundaries.
6. Trigger external verification without blending evidence classes.
7. Return insufficient evidence for a corpus gap.
8. Save a Knowledge Note after confirmation.
9. Create a Watch Topic after confirmation.
10. Show a useful secondary Weekly Brief based on actual usage.
11. Open a Knowledge Library topic page that shows current understanding,
    30/90-day changes, saved memory, contradictions, open questions, and
    original sources without requiring the old global Atlas.

PRM-16 implements the deterministic Weekly Brief V3 DTO and static renderer for
scenario 10 shape and failure isolation. Final acceptance still requires actual
usage evidence before claiming dogfood or release readiness.

## F. Dogfood Success

Over four weeks record:

- at least 30 real operator questions;
- useful answers;
- rejected or corrected answers;
- saved notes and watch topics;
- project or life decisions influenced;
- reacted posts recovered;
- time to useful answer;
- weekly cost;
- value score;
- friction score;
- whether the operator wants to continue using it.

Success is not "the system ran." Success requires evidence of useful answers
and reduced manual work.

PRM-17 adds deterministic workflow contracts and aggregate telemetry receipts
for future runtime activation, but does not start dogfood or scheduled jobs.

## G. PRM-18 Release Gate Receipt

PRM-18 adds a deterministic release/dogfood gate receipt:

- schema: `prm_release_gate.v1`;
- code: `evals/prm_release_gate.py`;
- current sanitized receipt:
  `evals/prm18_release_gate_receipt_2026-07-29.json`.

Current gate status:

- dogfood: `blocked`;
- release claimed: `false`;
- dogfood started: `false`;
- acceptance scenarios: 0 passed, 0 failed, 11 blocked;
- blocked evaluation areas: data, retrieval, generation, UI, and end-to-end;
- passed deterministic contract areas: tool, agent, privacy, and cost;
- active stop-ship blockers: unsupported claims and retrieval metric failure;
- human dogfood-start approval: missing.

The release gate is an evidence classifier, not a dogfood run. It does not run
live Telegram ingestion, reaction sync, LLM judges, browser automation,
external verification, report generation, full archive indexing, embeddings, or
external web research. PRM-19 cannot start until the human operator explicitly
approves dogfood start and accepts or clears the PRM-18 blockers.
