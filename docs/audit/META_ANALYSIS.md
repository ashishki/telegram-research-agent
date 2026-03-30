---
# META_ANALYSIS — Cycle 2
_Date: 2026-03-30 · Type: full_

## Project State

Phase 19 (T22–T27) implemented inline by Orchestrator; all tasks marked `[~]` — pending Light Review.
Next: Light Review PASS → Cycle 2 Deep Review at Phase 19 boundary.

Baseline: 12 pass, 0 skip (unchanged from Cycle 1; Phase 18 baseline held throughout Phase 19 implementation).

**Note on workflow:** T22–T27 were implemented in a single Orchestrator session without standard Light Review gate between tasks. This is a workflow violation flagged in CODEX_PROMPT.md. All Cycle 2 review steps must treat these tasks as unreviewed code.

---

## Open Findings

| ID | Sev | Description | Files | Status |
|----|-----|-------------|-------|--------|
| CODE-2 | P2 | `send_text()` hardcodes `parse_mode="HTML"` globally — non-digest callers (handlers sending plain text) still pass through HTML parse mode | `src/bot/telegram_delivery.py:73` | OPEN — risk reduced (digest content is now HTML per T19/T27 alignment), but non-digest text paths may mangle output |
| CODE-3 | P2 | `handle_digest` calls `send_text()` which forces `parse_mode="HTML"` on `row["content_md"]` — field name implies Markdown; content format must be verified as valid HTML for all DB rows | `src/bot/handlers.py:164` | OPEN — partially mitigated (T19 makes new digests HTML), but historical `content_md` rows may contain Markdown |
| CODE-4 | P2 | Bare `except Exception as e:` in insights block swallows DB and generation errors — only logs WARNING; caller sees `DigestResult` as successful even if insights failed silently | `src/output/generate_digest.py:461` | OPEN — improved (now logs with `%s` message vs. Cycle 1 bare except), but still suppresses all failure modes |
| CODE-5 | P3 | No delay between digest send and insights send — both dispatched in sequential try blocks with no sleep/backoff; Telegram rate limit may silently drop second message | `src/output/generate_digest.py:452–461` | OPEN — unchanged from Cycle 1 |

---

## PROMPT_1 Scope (architecture)

Review the following new and changed components for architectural coherence:

- **scoring pipeline** (`src/processing/score_posts.py`, `src/config/profile.yaml`, `src/config/scoring.yaml`): new multi-dimensional scoring engine wired into `ingest` pipeline; assess config coupling, fallback paths, and error propagation contract
- **digest generator rewire** (`src/output/generate_digest.py`): major restructure in T27 — scoring-first flow, `_fetch_scored_posts()`, `_build_scored_posts_for_prompt()`, word-count gate, insights second-message block; assess cohesion with prior DigestResult contract
- **schema migration** (`src/db/migrate.py`): T23 adds `signal_score`, `bucket`, `project_matches`, `interpretation` to posts; `tier`, `rationale` to `post_project_links`; new `quality_metrics` table — assess idempotency guarantees
- **prompt redesign** (`docs/prompts/digest_generation.md`, `docs/prompts/project_insights.md`): new variable surface `{scored_posts}`, `{noise_count}`, `{noise_summary}` replacing `{notable_posts}`; three-tier project inference replacing keyword-overlap — assess whether prompt contracts match generator call sites
- **NO_OVERLAP_NOTE elimination** (`src/output/generate_digest.py:145`, `src/integrations/github_crossref.py`): new guard `_append_github_section()` skips repos with `NO_OVERLAP_NOTE` — assess completeness; verify string does not surface in any output path
- **config files** (`src/config/profile.yaml`, `src/config/scoring.yaml`): assess YAML structure, weight sum invariant, bucket threshold ordering

---

## PROMPT_2 Scope (code, priority order)

1. `src/processing/score_posts.py` (new — T24: core scoring engine, no tests cover full path)
2. `src/db/migrate.py` (changed — T23: idempotency of new columns + quality_metrics table)
3. `src/output/generate_digest.py` (changed — T27: major rewire; CODE-4, CODE-5 live here)
4. `src/bot/telegram_delivery.py` (unchanged — CODE-2: parse_mode regression check, verify HTML-vs-Markdown contract holds for all send paths)
5. `src/bot/handlers.py` (unchanged — CODE-3: verify `handle_digest` send path is safe with historical `content_md` rows)
6. `src/integrations/github_crossref.py` (changed — NO_OVERLAP_NOTE guard; verify the sentinel value does not leak through any code path)
7. `src/config/profile.yaml` + `src/config/scoring.yaml` (new — structural validation: weights sum, bucket threshold ordering, YAML load safety)

---

## Cycle Type

Full — Phase 19 constitutes a complete phase boundary (T22–T27 all implemented). All six tasks are new/changed code with no prior deep review. Workflow violation (inline implementation without Light Review gates) elevates review priority.

---

## Notes for PROMPT_3

**Consolidation focus:**

1. **Scoring integrity**: The scoring engine is entirely new with minimal test coverage (only bucket assignment AC noted in T24). PROMPT_2 must verify whether at least 1 unit test covering bucket assignment actually exists — if not, this is a blocking finding.

2. **Parse-mode contract**: CODE-2 and CODE-3 have been open since Cycle 1. Phase 19 changed the digest format to HTML, which may have silently resolved or silently worsened these findings depending on delivery path. Cycle 2 must deliver a definitive FIXED or escalate to P1.

3. **Insights delivery**: CODE-4 and CODE-5 affect the new two-message delivery pattern introduced in T20/T27. The `except Exception` suppression of insights failure means users may silently receive only the digest with no indication that insights failed. PROMPT_3 should recommend a concrete fix (e.g., structured result with `insights_ok: bool` flag, or at minimum a fallback message to owner).

4. **Quality gates (Phase 19)**: Five quality gates are defined in tasks.md but none are covered by automated tests. PROMPT_3 should recommend at least Gate 3 ("no overlap found" never appears in output) and Gate 4 (word count ≤ 600) be converted to regression tests.

5. **Workflow debt**: T22–T27 implemented inline without Light Review. If PROMPT_2 finds any P1 finding in new Phase 19 code, the phase must be treated as BLOCKED pending fix before Cycle 2 is closed.
---
