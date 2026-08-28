# External Watch P0 Readiness

Status: active preparation; no collector is implemented

Updated: 2026-08-28

This is the executable preparation boundary for the UTD intelligence-layer
recommendation. It does not authorize network access, a service/timer, sidecar
creation, Telegram sends, or canonical database writes.

## What is complete in the repository

- ADR-008 defines confirmed-watch, evidence, delivery, privacy, and rollback
  boundaries.
- `evals/external_watch/` has a schema-checked 50-case evaluation inventory:
  35 development slots and 15 blind-holdout slots.
- `tools/validate_external_watch_eval.py` rejects public/private-data mistakes,
  duplicate IDs, unsupported labels, and an incorrectly claimed launch-ready
  manifest.

## Evidence still owned by the operator

The following cannot be generated from repository code and must not be
backfilled with synthetic evidence:

1. At least 15 RFX-8 operator smoke interactions and private labels.
2. A read-only parity receipt if a deployed Telegram runtime is relied on.
3. Real, sanitized UTD source examples: Localist payloads including all event
   instances/statuses/IDs, observed filters and response headers; plus the
   approved ISSO and Basic Needs HTML samples.
4. `notify|ignore|ambiguous` labels for the 50 fixture cases, including the 15
   blind cases, and an operator review of high-urgency cases.
5. Written approval for P1 shadow collection. P2 notification delivery needs a
   later, separate approval.

## Fixture intake

Keep raw source captures out of Git. Create a minimal sanitized fixture only
after manually inspecting it: remove people names, email addresses, analytics
tokens, cookies, tracking parameters, free-form comments, and unrelated page
content. Preserve only fields needed to prove identity, status, timestamps,
filter IDs/names, meaningful changes, headers, and source URL shape.

Run before accepting a fixture bundle:

```bash
python tools/validate_external_watch_eval.py --manifest evals/external_watch/manifest.v1.json
```

The validator reports readiness but deliberately exits non-zero if a manifest
claims `launch_ready=true` without all required independent evidence. A green
schema check is scaffolding evidence, not a permission to start P1 or dogfood.
