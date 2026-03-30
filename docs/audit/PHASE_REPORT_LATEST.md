# Phase 19 Report — Signal Intelligence Redesign
_Date: 2026-03-30_

## What was built

- **T22** — `src/config/profile.yaml` + `src/config/scoring.yaml`: personal taste and scoring weights extracted from LLM prompts into tunable config files
- **T23** — Schema migration: added `signal_score`, `bucket`, `project_matches`, `interpretation` to `posts`; `tier`, `rationale` to `post_project_links`; new `quality_metrics` table
- **T24** — `src/processing/score_posts.py`: 5-dimension scoring engine (personal_interest, source_quality, technical_depth, novelty, actionability); assigns bucket (strong/watch/cultural/noise); wired into `ingest` pipeline and as standalone `score` CLI command
- **T25** — `docs/prompts/digest_generation.md` rewritten: value-based bucket structure (Strong Signal / For My Projects / Watch List / Filtered Out) replacing 5-section taxonomy; ≤3500 chars, smart-colleague tone
- **T26** — `docs/prompts/project_insights.md` rewritten: structural/pattern inference (implement_now / relevant_pattern / watch tiers); confidence thresholds; eliminates "no overlap found"
- **T27** — `src/output/generate_digest.py` rewired: scoring runs before synthesis; LLM receives ≤6 pre-scored posts (not 150+); word-count gate (≤600 words); NO_OVERLAP_NOTE guard

## Test delta

Before: 12 passing
After: 12 passing (Phase 19 code has zero test coverage — CODE-1 P1 stop-ship)

## Review findings (Cycle 2)

- P0: 0
- P1: 1 — CODE-1: zero test coverage for scoring engine and digest rewire (stop-ship, Fix Queue FIX-1)
- P2: 5 — CODE-2 (parse_mode), CODE-3 (handle_digest HTML), CODE-4 (exc_info missing), CODE-6 (duplicate insights delivery), CODE-8 (quality_metrics never populated)
- P3: 2 — CODE-5 (no Telegram delay), CODE-7 (cluster_coherence stub undocumented)

## Health

⚠️ Yellow — Phase 19 BLOCKED on T28 (unit tests). Core scoring logic works (smoke test passed), but CODE-1 is a stop-ship finding. No P0 issues. P2 batch queued for next sprint.

## Next phase

Phase 19 close-out: T28 (unit tests, Fix Queue FIX-1) → P2 batch fixes (CODE-2, CODE-3, CODE-4, CODE-6, CODE-8) → Cycle 3 → Phase 19 marked complete.
Phase 20 (Phase 2 of strategic redesign): Interpretation pre-compute (Haiku per-post), quality_metrics population, study recommendations upgrade.
