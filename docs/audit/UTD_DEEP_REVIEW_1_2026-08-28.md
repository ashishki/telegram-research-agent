# UTD Deep Review 1 — 2026-08-28

Status: partial_pass_with_explicit_operator_evidence_gates

## Scope reviewed

- UTD-1 profile and preview-watch UX.
- Public source-family evidence for Calendar/Registrar/Career/AI, ISSO and Basic Needs.
- Relevance, urgency, duplicate, stale-source, benefit and spouse/family safety policy.
- Active Telegram one-bot boundary.
- Provider/context egress boundary.
- Focused CI and retrofit test boundary.

## UTD-1 result

PASS for implementation scope.

Observed product contract:

- one existing PRM Telegram bot;
- local 30-minute UTD draft before durable save;
- exact confirmation required before durable profile/watch intent;
- cancellation/expiry scrubs temporary proposal payload;
- preview includes categories, source families, filters, America/Chicago timezone, cadence, daily cap, expiry, pause and mute controls;
- ordinary archive queries remain on the archive path;
- UTD questions that require fresh evidence fail closed while live UTD sources are disabled;
- no second bot, report timer or hidden durable preference learning was introduced.

## Privacy review

PASS with residual transport-evidence gate.

- Profile details remain in local PRM state and are not placed in public fixtures.
- Telegram callback namespaces for UTD remain isolated from legacy write callbacks in PRM mode.
- OpenAI adapter is isolated and default-deny.
- Provider egress and archive-context egress require separate explicit gates.
- No provider call was performed as part of UTD-1/2/3 preparation.
- No raw private Telegram/archive data was added to public evidence.

## Source review

PARTIAL PASS.

Current public primary-source families were verified sufficiently to remove generic-university assumptions:

- Comet Calendar / Registrar for programme and academic changes;
- Career Center for career events;
- UTD department/research/IT/engineering calendar surfaces for AI events;
- ISSO / International Center for international-student requirements and programming;
- Basic Needs Resource Center for student resources and benefit caveats.

However, UTD-2 acceptance still requires sanitized raw Localist JSON plus observed transport headers and minimized raw HTML fixtures. Those artifacts do not exist yet, so `live_source_samples_verified` must remain false.

## Relevance review

PARTIAL PASS.

The deterministic policy now covers:

- new/updated/cancelled/reinstated;
- recurrence and duplicate identity;
- date/location/deadline changes;
- disappearance/return;
- stale, timeout, 429 and schema drift;
- prompt injection;
- eligibility;
- past events;
- unsupported savings/benefit claims.

Spouse/family remains strict: explicit eligibility is required. Benefit claims remain strict: no inferred savings or government/off-campus eligibility.

The 50-case manifest still correctly says `pending_operator`; an AI-authored default policy is not represented as human evaluation evidence.

## CI / regression review

PASS.

During this phase the existing focused CI exposed three pre-existing contract mismatches. They were resolved without weakening safety checks:

- PRM safe mode once again returns the legacy-callback rejection acknowledgement while blocking the write;
- the replay tool once again exposes the backward-compatible `replay_query` fixture API expected by the focused regression suite;
- public replay summaries retain explicit privacy booleans and no raw query/source leakage.

Latest push CI after these fixes passed:

- focused PRM tests;
- retrofit boundaries;
- MAT safety holdouts;
- Playbook contract validation;
- public evidence boundary.

## Forbidden-action review

PASS.

This phase introduced none of the following:

- live source poller;
- timer/systemd UTD watcher;
- Telegram notification delivery;
- production database migration;
- browser automation;
- credential or cookie storage;
- university-system mutation;
- auto-apply/register/book/purchase action;
- dogfood/release claim.

## Decision

UTD-1 is implementation-complete with residual human/product gates. UTD-2 and UTD-3 are preparation-complete but evidence-incomplete: raw sanitized source contracts and human case labels remain mandatory.

UTD-4 MUST remain blocked. No source-bounded shadow collector should be implemented or run until:

1. sanitized Localist JSON + transport headers are captured and reviewed;
2. minimized ISSO and BNRC source fixtures are captured and reviewed;
3. all 50 evaluation cases have explicit human outcomes;
4. the operator explicitly approves real source polling after reviewing those artifacts.

This review therefore closes all code/documentation work that can be completed safely without fabricating human evidence or crossing the real-polling gate.
