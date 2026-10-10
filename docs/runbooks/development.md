# Development Verification

## Current PA documentation/verification — 10 October2026

Use [TEST_STRATEGY](../TEST_STRATEGY.md), [CODEX_PROMPT](../CODEX_PROMPT.md) and [master integration](../verification/PAI-master-integration-20261010.md). Source0fbcfd1 is checked/reviewed; no old NEXT-TASK/source/provider assumption below overrides the active assignment. Full historical pytest is prohibited; model/CI/live/human evidence distinct.

Status: active
Last updated: 2026-08-12

Use deterministic tests, task/reference validation, and `git diff --check` for
PRM-UX work. Do not use development verification to start services, run live
ingestion, alter the canonical database, perform external research, or claim
dogfood/release status.

The current operator workflow is documented in `docs/operator_quickstart.md`.
