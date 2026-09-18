# PRM-SN limited-pilot / rollback packet (not an authorization)

Status: prepared for human review only. This document does **not** start a pilot,
enable a timer, change `.env`, send Telegram messages, or authorize provider
egress. A separate human decision must select the exact reviewed working diff
and approve each runtime action below.

## Proposed bounded observation

- Code identity: base `cee8baae3b8a41f571bd689f2dadf7e6e981863f`; accumulated
  source/test working-diff SHA-256
  `d0fecb9273c769a56c3ff081fe3b410eb7389b3c1f58933c5fde3300d7b0ce52`.
  The deterministic derivation and complete file inventory are in
  `docs/audit/PRM_SN_DR5_SCOPE_2026-09-17.json`; it includes tracked diffs and
  untracked source/test files while deliberately excluding this packet and
  receipts to avoid a self-referential identity. Any covered code/test edit
  invalidates this packet until a reviewer records a replacement hash.
- Duration: 14 consecutive calendar days, one owner chat only.
- Sources: existing public, allowlisted UTD Calendar, ISSO and Basic Needs
  adapters only; no arbitrary URLs, private archive data, provider synthesis,
  embeddings, media, or source expansion.
- Actions: confirmed profile only; one on-demand edition may be requested by
  the owner. This packet does not start, enable or alter a runtime. If a runtime
  was separately enabled, a newly confirmed active profile may be read on its
  next run, subject to its kill switch and delivery gates; the operator must
  verify that existing state before any pilot decision. Pause and unsubscribe
  use exact chat-bound confirmation previews.
- Budget: at most 5 candidate units/day, one ordinary digest/day, at most 3
  known-failure attempts/item; ambiguous outcomes are `unknown` and never
  automatically resent. No paid-provider budget is authorized (`$0`).

## Preflight evidence required from the human operator

1. Confirm exact source/diff hash and review receipts DR-1 through DR-5.
2. Confirm owner chat identity locally without placing it in this repository.
3. Observe and record the current scoped service/timer state and the local
   EnvironmentFile control values (delivery enablement and kill switch) without
   placing them in this repository. Neither this packet nor profile confirmation
   may assume runtime is disabled; separately approve any temporary change.
4. Create only a disposable/derived sidecar location and verify no production
   database migration or archive/provider egress is implicated.
5. Record start time, selected sources, expiry, daily cap and timezone in an
   operator-only log. This repository must receive aggregate evidence only.

## Observations and stop conditions

Record denominators: collection attempts, source-success/error counts,
candidates, selected candidates, sends, deferred, unknown, duplicate blocks,
daily-cap blocks, quiet-hour blocks, pause/mute/unsubscribe blocks, and user
feedback counts. Inspect actual rendered text, source links, source coverage,
timezone/DST behavior and receipts.

Immediately stop collection and delivery if a kill switch is set, an unapproved
source/egress is attempted, an unconfirmed/cancelled/expired profile can poll
or send, a cap is exceeded, an ambiguous send is replayed, private data appears
outside approved local storage, or a rollback action cannot preserve receipts.

## Rollback procedure

1. Set delivery off and kill switch on; do not delete outbox or receipt rows.
2. Pause/cancel the confirmed subscription through an explicit lifecycle
   action; retain the event history and compatible sidecar receipts.
3. Stop the scoped runtime only if it was separately started for the pilot.
   Do not touch legacy timers/services.
4. Export a privacy-safe aggregate receipt: exact code identity, window,
   counters, failures, unknown outcomes and operator decision. Do not export
   chat content, tokens, Telegram archives or raw source payloads.
5. Re-enable nothing automatically. Any retry/reconciliation of `unknown`
   requires a new explicit operator decision.
