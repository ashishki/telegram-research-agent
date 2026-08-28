# Review Policy

## PRM-MAT review boundary

PRM-MAT-0 through PRM-MAT-16 require evidence-backed review; risky tasks require critic/holdout/property checks as declared in `docs/tasks.md`. PRM-MAT-17 needs explicit bounded smoke approval; PRM-MAT-18 needs explicit four-week validation-start approval. No fixture, local runtime receipt or LLM judge substitutes for operator labels.

## PRM-MAT Deep Review Protocol

Use the existing Playbook deep-review/audit mechanism; this section only fixes
when PRM-MAT invokes it. Do not replace its audit checklist, evidence format,
or completion authority with a new local protocol.

Run one batched deep review after each completed block:

- **A:** PRM-MAT-1 through PRM-MAT-5 — canonical context, routing, lens,
  project context, answer DTO, and Telegram UX.
- **B:** PRM-MAT-6, PRM-MAT-7, PRM-MAT-11 — durable proposals, receipts, and
  queryable saved knowledge.
- **C:** PRM-MAT-8 through PRM-MAT-9 — archive freshness and reaction path.
- **D:** PRM-MAT-10 through PRM-MAT-12 — primary-source verification and
  professional workflow integration.
- **E:** PRM-MAT-13 through PRM-MAT-16 — recap, evaluation, operations,
  privacy/cost, documentation, and CI.
- **F:** before PRM-MAT-17, and again after PRM-MAT-18 evidence review —
  smoke/validation readiness and post-validation decisions.

Also invoke an immediate Playbook deep review before continuing after a task
that changes or enables persistent schema/write behavior, production migration,
provider/raw-text egress, live network verification, archive/reaction schedule,
trust policy, backup/restore boundary, dogfood start, release claim, or
compatibility deletion/archive/move. This includes PRM-MAT-3, -6, -7, -8, -10,
-15, and -17 whenever their scoped implementation reaches that boundary.

When the Playbook protocol calls for an exec-based Codex reviewer, request
`gpt-5.6-terra` with `high` reasoning effort. Record the exact command, the
effective model/effort reported by the runtime, reviewer input scope, findings,
required corrections, and re-verification result. If the runtime cannot honor
that model/effort selection, record the mismatch and do not represent the
review as Terra/high. The review remains read-only unless a separate approved
fix task is started; it cannot approve human gates or completion.

Status: current
Last updated: 2026-08-28
Playbook SHA: 965612aa463fca1a35a55104633d0e09da33d615
Historical retrofit pin: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0 (stale)

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

## UTD Assistant Deep-review Gates

UTD work uses **batched** deep reviews at phase boundaries. Do not run a full
deep review after every small task or UI copy change. A focused test critic and
ordinary task verification remain sufficient inside a phase unless an immediate
safety trigger below applies.

| Gate | Runs after | Required before | Review focus |
| --- | --- | --- | --- |
| `UTD-DR-1` | UTD-1 profile/watch UX, UTD-2 source-contract capture, and UTD-3 labelled relevance policy | UTD-4 shadow collector | one-bot contract, explicit confirmation, programme/career/family scope, source/eval truth, privacy and no-notification boundary |
| `UTD-DR-2` | UTD-4 shadow collector and UTD-5 shadow-quality evidence | UTD-6 Telegram delivery | source safety, diff/idempotency, stale/429 behavior, precision/recall, duplicate and urgency controls, kill switch, delivery-ready UX |
| `UTD-DR-3` | UTD-6 controlled delivery and UTD-7 feedback-calibration evidence | any expansion of sources, caps, autonomy, dogfood claim, or retention change | real usefulness, notification burden, spouse/family eligibility, feedback proposals, privacy receipts and residual-risk decision |

An immediate review is still required before continuing if a UTD change would:

- enable real source polling, Telegram delivery, provider egress, or a timer;
- create a durable profile/watch write path or alter its confirmation semantics;
- change sidecar retention, source allowlists, SSRF/redirect protections, or
  handling of credentials/12twenty email;
- make a dogfood/release claim, alter notification caps, or add an external
  source family.

Each UTD deep review is recorded under `docs/audit/` with changed scope,
evidence, UX findings, privacy findings, corrections, verification, and
unresolved operator approvals. It is read-only and cannot substitute for an
operator approval or private labels.

### UX is a release-quality input, not a polish pass

Every UTD deep review must inspect these operator-facing flows using sanitized
fixtures or private operator evidence, never raw personal data:

1. **ASK:** a UTD question returns a brief answer first, primary source links,
   freshness/status in plain language, and a truthful fail-closed boundary.
2. **WATCH:** the bot shows an understandable preview before confirmation:
   what it watches, why it matches programme/career/family context, cadence,
   timezone, cap, expiry and how to pause/mute.
3. **NOTIFICATION:** an alert explains why it is relevant, distinguishes a
   deadline/cancellation from an opportunity, avoids technical internals, and
   exposes useful/not useful, mute and pause without surprise profile changes.
4. **One-bot coherence:** AI archive research and UTD assistance remain
   distinguishable by wording/source but feel like one assistant; no second bot,
   duplicate timer messages, report-era jargon, or competing notification paths.

The reviewer must record concrete UX friction and correct P0/P1 issues before
the next phase. A technically correct collector that produces noisy, unclear,
or ineligible notifications does not pass a deep-review gate.

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

## Test Tiers

Use `docs/TEST_STRATEGY.md` and `tools/test_tiers.py` to choose the smallest
appropriate deterministic test tier. The operator prohibits full-suite runs
because the suite contains unrelated legacy coverage; do not use `full` or a
full-suite block-review command as task evidence.

- `focused-prm` for narrow PRM RAG/assistant changes;
- `fast-contract` for shared contract, router, telemetry, and privacy-boundary
  changes;
- `ops-date-sensitive` for product ops validation and known date-window
  failures;
- `block-review` for Playbook validation, targeted/integration checks selected
  for the block, and whitespace diff validation before closing a deep-review
  block.

Known failures must be isolated and named exactly. Do not delete, archive, move,
or weaken tests merely because coverage is broad or one ops check is
date-sensitive; collect retrofit candidates for PRM-MAT-16.
