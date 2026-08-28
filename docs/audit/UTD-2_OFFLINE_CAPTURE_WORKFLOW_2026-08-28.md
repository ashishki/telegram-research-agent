# UTD-2 Offline Capture Workflow — 2026-08-28

Status: implemented tooling, pending human source capture

## Purpose

Convert UTD-2 from an informal evidence request into a reproducible, privacy-safe offline workflow without enabling live polling, timers, delivery, provider egress, production migrations, or external jobs.

## Workflow

1. Human opens the public UTD source in an ordinary browser.
2. Human copies only the minimum public fields needed to prove the contract.
3. Human removes cookies, authorization data, personal identifiers, unrelated page content and session metadata.
4. Human stores the sample under `tests/fixtures/external_watch/` using `utd_source_fixture.v1`.
5. Run `python3 tools/utd_evidence_review.py validate-fixture <path>`.
6. Only after manual inspection may the fixture be referenced by `evals/external_watch/manifest.v1.json`.

For Calendar/Localist, capture event identity, instance identity/times, recurrence/status/update fields, pagination/filter identifiers where visible, and only non-sensitive response headers required for adapter design. For ISSO and Basic Needs, capture the stable main-content excerpt, canonical URL, and material deadline/resource/eligibility fields.

## Operator review

Generate a blank 50-case review worksheet with:

`python3 tools/utd_evidence_review.py review-sheet --manifest evals/external_watch/manifest.v1.json --output data/evals/private/utd_operator_review.json`

The generated file is private/gitignored. Tooling intentionally leaves every operator label blank and never upgrades `pending_operator` to `reviewed_operator` automatically.

## Gate

UTD-2 remains pending until real sanitized source samples exist and are manually checked. UTD-3 remains pending until the human operator labels all 50 cases. UTD-4 remains blocked until UTD-DR-1 can review that real evidence and explicit polling approval exists.
