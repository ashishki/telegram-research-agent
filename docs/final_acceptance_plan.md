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
invented query may be labelled gold evidence.

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

These thresholds are not passed yet.

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
