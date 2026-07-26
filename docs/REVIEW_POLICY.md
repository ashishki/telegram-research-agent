# Review Policy

Status: proposed
Last updated: 2026-07-26
Playbook SHA: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0

## Authority

This policy governs the Personal Telegram Research Memory retrofit and future
implementation tasks. The human operator is the only completion authority.
Codex sessions may implement, verify, and propose completion evidence, but they
do not approve product readiness, privacy posture, dogfood start, or permanent
memory/profile changes.

## Execution Model

- Bootstrap and implementation use Codex Direct in the repository.
- Optional child agents are read-only reviewers, Test Critics, privacy
  reviewers, scoped fix agents, or documentation sync assistants.
- Child agents must not commit, push, self-review, approve completion, mutate
  production data, or grant release readiness.
- Subagents are optional after bootstrap; they are not required for every task.

## Review Triggers

Test Critic is required for:

- RAG indexing, retrieval, reranking, and generation changes;
- assistant tool routing, tool schemas, and agent loop boundaries;
- migrations, rollback, idempotent workflow changes, and telemetry;
- privacy, logging, provider-egress, and external-skill decisions;
- Weekly Brief V3 or Knowledge Library user-facing releases.

## Review Batching

Deep review is batched by implementation block by default. A task marked
Critic-Required: required must be covered by the next block review, but it does
not require spawning a separate deep-review agent immediately after that single
task.

Default block review gates:

- PRM-1 through PRM-2: data readiness, document identity, privacy-safe corpus
  inventory.
- PRM-3 through PRM-4: full-archive FTS baseline and first assistant search
  vertical slice.
- PRM-5 through PRM-6: reaction fast lane and selective enrichment.
- PRM-7 through PRM-8: retrieval evaluation, vector/hybrid ADR, and any
  conditional hybrid implementation.
- PRM-9 through PRM-12: assistant router, grounded answers, external
  verification, and confirmation-gated writes.
- PRM-13 through PRM-17: Knowledge Library, project context, learning-state
  migration, Brief V3, and autonomous operations.
- PRM-18 through PRM-20: release gate, dogfood evidence, cleanup, and archive.

Immediate deep review is still required before continuing when a change touches:

- raw Telegram text egress or provider data boundary;
- external skill approval;
- unsafe write or confirmation bypass;
- schema migration against production data;
- vector backend adoption;
- dogfood start or release claim;
- deletion, archive, or movement of compatibility files.

For token control, ordinary block review should inspect the accumulated diff,
task evidence, changed tests, and relevant contracts for the block. It should
not reread all historical IRX material unless a concrete reference or failure
requires it.

Privacy review is required for:

- any new LLM provider or embeddings provider;
- any raw Telegram text egress;
- logging/transcript changes;
- web verification storage;
- external skill trust approval;
- public fixture generation.

Human approval is required before:

- accepting the product pivot ADR;
- starting implementation beyond Playbook retrofit;
- marking candidate eval queries as gold;
- enabling external skills;
- running full archive LLM backfills;
- adopting a vector backend;
- dogfood start;
- deleting or archiving compatibility files.

## Completion Evidence

Each task must record:

- changed files;
- verification commands and exact results;
- known failures and warnings;
- privacy/cost boundary evidence when relevant;
- links to updated docs or receipts;
- unresolved human approvals.

Warnings remain warnings. Fixture-only validation must not be described as live
operator validation.
