# PRM-19 Dogfood Plan — Real Operator Usefulness Evidence

Status: proposed; PRM-19 not started
Date: 2026-08-12

## Relationship To Canonical PRM-19

This document defines the product-usefulness evidence model for the existing
PRM-19 task. It does not start dogfood and does not create a second dogfood
task.

PRM-19 remains blocked until:

- the minimum PRM-UX dogfood-start slice is complete;
- explicit human dogfood-start approval is recorded;
- the operator accepts the evidence fields and success/failure criteria.

## Minimum Real-Question Set

Collect at least 30 real questions:

- 5 AI systems questions;
- 5 project-application questions;
- 5 career/portfolio questions;
- 5 product/enterprise questions;
- 5 writer/editor questions;
- 5 learning questions.

Questions must come from real operator use. Generated questions can be smoke
tests but not PRM-19 usefulness evidence.

## Interaction Receipt

For each question, record privacy-safe metadata only:

```yaml
question_id:
asked_at:
surface: telegram | cli
input_kind: text | voice_transcript
selected_professional_lens:
selected_project:
intent_chosen:
clarification_required: true | false
answer_latency_seconds:
source_count:
evidence_classes:
  - telegram_archive
  - curated_memory
external_verification_status: not_needed | required_not_run | approved_run | unavailable
useful: yes | partial | no
trust: high | medium | low
rephrase_required: true | false
incorrect_or_irrelevant_evidence: true | false
saved_note_watch_action: none | knowledge_note | watch_topic | project_link | action | experiment
decision_or_action_influenced:
time_saved_estimate_minutes:
operator_correction:
feedback_notes:
privacy:
  raw_post_text_recorded: false
  provider_payload_recorded: false
  durable_write_confirmed: true | false
```

Do not store raw Telegram post bodies in dogfood docs. If source examples are
needed, cite stable source refs or Telegram URLs without copying private text.

## Product Metrics Requiring Approval

Proposed targets:

- at least 70% useful or partially useful answers;
- at least 80% normal questions handled without manual command;
- at least 90% source-derived claims have supporting citations;
- reacted posts are searchable after the next successful reaction refresh;
- no-answer preferred over unsupported current/high-stakes claims;
- median time to useful answer under two minutes;
- default Telegram output fits comfortable mobile reading;
- fewer than 20% questions require rephrasing;
- at least four concrete project/career/writing/learning actions emerge during
  four weeks.

Do not treat these as passed before real operator labels exist.

## Weekly Review

Each week record:

- question count by category;
- useful / partial / no counts;
- trust distribution;
- median latency;
- manual command rate;
- source/citation issues;
- provider cost and provider-call count if approved;
- save/watch/action counts;
- most common friction;
- one allowed fix for next week.

## One-Fix-Per-Week Rule

During PRM-19, make at most one product fix per week unless there is a privacy,
provider-egress, unsafe-write, data-loss, or severe false-claim incident.

Rationale: dogfood should measure the product, not constantly rewrite it.

## Cost / Time / Friction Tracking

Track:

- answer latency;
- time saved estimate;
- manual rephrase count;
- number of command overrides;
- provider calls/cost when approved;
- failed/blocked turns;
- feedback actions used;
- answers abandoned because they were too long or too shallow.

## Stop Conditions

Stop dogfood and require operator review if:

- raw private corpus or provider payload appears in committed docs/logs;
- durable writes occur without confirmation;
- provider egress happens outside approved gates;
- current/high-stakes claims are answered as current without verification;
- archive refresh or reaction sync corrupts canonical state;
- the assistant repeatedly routes professional questions to generic chat;
- the operator no longer wants to continue the trial.

## Success Criteria

PRM-19 success requires:

- 30 real labelled questions;
- explicit operator usefulness labels;
- evidence that at least four concrete project/career/writing/learning actions
  were influenced;
- privacy/cost boundaries respected;
- continuation decision recorded by the operator.

Success is not "the service ran".

## Failure Criteria

PRM-19 should be judged failed or not-yet-successful if:

- fewer than 30 real labelled questions are collected;
- usefulness falls below the approved threshold;
- the operator mainly falls back to manual commands/search;
- source support is too weak for trust;
- no concrete professional action emerges;
- the product creates more friction than manual search.

