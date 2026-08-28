# ADR-008: Confirmed External Watch Boundary

Status: proposed; P0 specification only

Date: 2026-08-28

Decision owner: human operator

## Context

PRM has confirmation-gated `watch_topic` memory events, but those events are
not executable monitoring. Current-fact questions correctly fail closed rather
than fetching live sources. The UTD intelligence-layer research recommends a
small, source-specific external-watch capability only after retrofit evidence,
real sanitized source samples, and an independently reviewed fixture set exist.

This ADR intentionally specifies the boundary before any collector, network
fetch, timer, sidecar migration, Telegram delivery, or production-data change.

## Proposed decision

If later accepted, external watch is a single PRM capability with these rules:

- A typed watch proposal is displayed before polling begins. It names sources,
  exact filters, audience/eligibility, `America/Chicago` timezone, cadence,
  daily cap, expiry, and delivery policy.
- Only an explicitly confirmed, active, unexpired watch is eligible for a
  collector run. `watch_topic` alone is never interpreted as permission to
  fetch or notify.
- External observations are derived private data in a dedicated, gitignored
  SQLite sidecar. `personal_memory_events` remains the canonical record of
  confirmed intent; the Telegram archive remains unchanged.
- Each adapter is an allowlisted primary source with bounded requests,
  DNS/redirect/private-address protections, content-type and size limits,
  conditional-fetch support where verified, rate-limit backoff, and no browser
  automation or credential storage.
- A failed or stale fetch is health evidence, never a deletion/change event.
- A notification requires stable identity, a material field change, current
  source evidence, relevance-policy approval, and an idempotency receipt.
  Default delivery is at most one daily digest with at most five items; urgent
  cancellation/deadline overrides must be source-supported.
- ASK can use only fresh cited primary evidence from an accepted adapter;
  otherwise the existing `needs_external_verification` result remains.
- The P1 shadow collector sends no Telegram messages and makes zero model
  calls. P2 delivery requires separate approval after shadow evidence.

## Proposed sidecar model

The eventual sidecar uses `watch_runs`, `source_snapshots`, `external_items`,
`item_versions`, `change_events`, and `notification_ledger`. Receipts must use
an idempotency key of `watch_id + change_id + policy_version`. Raw payloads, if
temporarily retained, are private and gitignored; normalized facts, hashes and
provenance are sufficient for long-lived diagnostics.

## Non-goals

- unrestricted web crawling or a general fetch tool;
- a second Telegram bot, browser automation, credential scraping, or mutation
  of UTD systems;
- LLM-first change detection, automatic preference learning, auto-apply,
  registration, booking, purchase, or external action;
- hosted vector services, canonical PRM/archive migrations, or provider egress
  as part of this decision.

## Gates and rollback

Before P1, record: completed RFX-10 review; 15--20 private operator smoke
labels for RFX-8; a read-only deployment-parity receipt when a runtime is in
scope; real sanitized UTD payload/header/filter samples; and a fixture/eval
manifest with 35 development and 15 blind, operator-labelled cases. P1 may run
only in shadow mode and must be disableable by stopping its separate timer and
feature flag. P2 delivery requires measured shadow precision and a separate
operator approval. Neither phase starts PRM-19 dogfood or authorizes release
claims.

## Consequences

No runtime behavior changes with this ADR while it is proposed. Its purpose is
to prevent a confirmed memory noun from being mistaken for authorization to
poll or notify.
