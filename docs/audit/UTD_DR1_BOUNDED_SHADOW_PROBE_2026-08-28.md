# UTD-DR-1 — Bounded Shadow Probe Authorization — 2026-08-28

Status: implementation_probe_authorized; phase_completion_still_requires_human_labels

## Review decision before real polling

The operator explicitly authorized acting on the user's behalf to maximize useful progress. Real polling is therefore authorized only for a bounded shadow verification of the allowlisted public sources already captured under UTD-2.

The probe is permitted because:

- UTD-1 confirmation/profile boundaries are unchanged;
- UTD-2 now has real sanitized Localist, ISSO and Basic Needs source-contract evidence;
- the collector reads the PRM profile through the existing SQLite read-only boundary;
- the probe uses an ephemeral synthetic confirmed profile, not the production PRM DB;
- derived state is written only to an ephemeral sidecar SQLite DB;
- Telegram delivery, provider egress, credentials/authenticated systems, production DB migration/write and timers are absent;
- source failures/429/schema drift update source health and do not synthesize disappearance/deletion;
- focused/adversarial tests cover allowlist/SSRF-like URLs, redirects, size/content-type, 429, identity, DST offsets, idempotency, cancellation/reinstatement and spouse/family explicit eligibility.

## Residual gate

This document does **not** mark UTD-DR-1 complete. UTD-3 still requires the human operator's 50 notify/ignore/ambiguous judgments. The bounded probe is implementation evidence only and cannot authorize Telegram delivery, timer enablement, dogfood/release claims or UTD-5 completion.
