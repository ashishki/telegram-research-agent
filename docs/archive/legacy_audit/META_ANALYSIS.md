---
# META_ANALYSIS — Cycle 3
_Date: 2026-03-30 · Type: targeted_

## Project State

Phase 1 (Baseline Stabilization) of Roadmap v2 is in progress; the immediate preceding legacy work (Phase 19, T22–T27 + Phase 20, T34) closed all P1/P2 Cycle 2 stop-ship findings, leaving the repo unblocked but still requiring Phase 1 baseline documentation and metrics capture before Phase 2 scoring work begins.
Next: Phase 1 — deliver baseline stabilization packet (runtime/doc reconciliation, metrics schema, CI/CD health confirmation).

Baseline: **44 pass, 0 skip** (Cycle 2 was 12 pass; Phase 19-p2 raised to 37, then T34 raised to 44).
Delta from previous cycle: +32 tests — significant new coverage added for scoring engine, digest generator, handlers, delivery, and router.

---

## Open Findings

| ID | Sev | Description | Files | Status |
|----|-----|-------------|-------|--------|
| CODE-1 | P1 | Zero test coverage for scoring engine and digest rewire (T24 AC unmet) | `tests/test_score_posts.py`, `tests/test_generate_digest.py` | **CLOSED** — both files now exist with substantive coverage (199 and 376 lines respectively); bucket boundary, cultural override, quality_metrics population, and insights traceback tests confirmed present |
| CODE-2 | P2 | `send_text()` hardcoded `parse_mode="HTML"` — non-digest callers could not override | `src/bot/telegram_delivery.py` | **CLOSED** — T29 added optional `parse_mode` param (default HTML); `test_telegram_delivery.py` confirms override works |
| CODE-3 | P2 | `handle_digest` sent `content_md` via HTML parse mode — historical Markdown rows at risk | `src/bot/handlers.py` | **CLOSED** — T30 wires `handle_digest` to `parse_mode=None`; `test_handlers.py` asserts call contract |
| CODE-4 | P2 | Bare `except Exception` in insights block swallowed traceback | `src/output/generate_digest.py` | **CLOSED** — T31 adds `exc_info=True`; test confirms traceback appears in log |
| CODE-5 | P3 | No delay between digest send and insights send — Telegram rate limit risk | `src/output/generate_digest.py:533–548` | **OPEN** — no `time.sleep()` added between the two sequential `send_text` calls; still two back-to-back dispatches with no backoff |
| CODE-6 | P2 | `handle_run_digest` called `generate_recommendations()` after `run_digest()` already triggered it internally — duplicate delivery | `src/bot/handlers.py` | **CLOSED** — T32 removed the redundant call; `test_handlers.py:test_handle_run_digest_relies_on_run_digest_delivery_only` asserts `generate_recommendations` not called |
| CODE-7 | P3 | `scoring.yaml cluster_coherence` documented as active weight but stubbed at 0.5 permanently — misleads operators | `src/config/scoring.yaml`, `src/processing/score_posts.py` | **OPEN** — no change observed in T29–T34; stub still present |
| CODE-8 | P2 | `quality_metrics` table created but never populated — no observability row after digest runs | `src/output/generate_digest.py`, `src/db/migrate.py` | **CLOSED** — T33 adds `_store_quality_metrics()` called after both the early-exit and normal paths; `test_generate_digest.py:test_run_digest_populates_quality_metrics` verifies row values |
| ARCH-3 | P3 | `docs/architecture.md` has no mention of scoring engine, new DB columns, or `quality_metrics` table | `docs/architecture.md` | **OPEN** — no architecture doc update observed in T29–T34 or roadmap-v2 bridge commit |
| ARCH-4 | P3 | `scoring.yaml cluster_coherence` references non-existent per-post silhouette data | `src/config/scoring.yaml`, `src/processing/score_posts.py` | **OPEN** — same root as CODE-7; no fix |
| ARCH-5 | P3 | `docs/spec.md` section 11 prompt contract not updated for T27 variable rename | `docs/spec.md` | **OPEN** — `de84dcc` touched `docs/spec.md` but only added roadmap bridge note; T27 variable contract still unverified |
| ARCH-NEW-1 | P2 | `src/llm/router.py` (T34) only routes `synthesis` to STRONG; `per_post` routing is implemented but `generate_digest.py` only calls `route("synthesis")` — the per-post interpretation path (Phase 3 requirement) is not wired | `src/llm/router.py`, `src/output/generate_digest.py` | **OPEN** — partial implementation; router exists but per-post dispatch is unused; qualifies as Phase 3 work, but gap should be documented |
| ARCH-NEW-2 | P3 | `src/llm/client.py` cost logging is DEBUG-only with no persistent store — cost-per-run metric exists only in logs, not in `quality_metrics` or any queryable table | `src/llm/client.py`, `src/output/generate_digest.py` | **OPEN** — contradicts Phase 3 success criterion "cost per run bounded and explainable"; acceptable as Phase 1 state but must be a Phase 3 entry requirement |
| ROAD-1 | P2 | Roadmap v2 Phase 1 success criteria are not yet met: baseline metrics have not been captured for a full run, `docs/architecture.md` and `docs/spec.md` still do not reflect the current system, and no documented "baseline behavior" artifact exists | `docs/architecture.md`, `docs/spec.md`, `docs/tasks.md` | **OPEN** — the Roadmap v2 bridge commit (de84dcc) updated CODEX_PROMPT and workflow prompts but did not produce the Phase 1 deliverables (baseline run artifact, aligned architecture doc, quality metrics schema docs) |

---

## PROMPT_1 Scope (architecture)

- **router.py / Phase 3 partial wiring**: `src/llm/router.py` introduces `route()` with CHEAP/MID/STRONG tiers but only the `synthesis` path in `generate_digest.py` is wired; assess whether this constitutes premature Phase 3 work and whether the partial wiring creates any contract ambiguity or test surface gaps
- **cost logging gap**: `src/llm/client.py` emits DEBUG-level cost estimates but no persistent cost-per-run record exists; assess whether Phase 1 baseline stabilization should capture this as a blocking gap or a deferred Phase 3 concern
- **architecture doc drift (ARCH-3)**: `docs/architecture.md` still describes the pre-scoring-engine system; assess what the minimum update is to unblock Phase 1 exit criteria without triggering Phase 2+ scope
- **spec.md prompt contract (ARCH-5)**: verify whether the T27 `{scored_posts}` / `{noise_count}` / `{noise_summary}` variable rename is reflected in `docs/spec.md` section 11; if not, classify as Phase 1 documentation debt

---

## PROMPT_2 Scope (code, priority order)

1. `src/llm/router.py` (new — T34: multi-model routing, only partially wired; no integration tests; check for routing gaps and confirm test coverage is adequate for the dispatcher logic)
2. `src/llm/client.py` (changed — T34: model override + cost logging; verify DEBUG log path, `_record_usage` integration, and that cost is not silently suppressed when model override is absent)
3. `src/output/generate_digest.py` (changed — T33/T34: `_store_quality_metrics` added, `route("synthesis")` wired; verify quality_metrics store is called in all exit paths including the early-exit branch at line ~447; verify CODE-5 sleep gap still open)
4. `src/processing/score_posts.py` (regression check — CODE-7/ARCH-4: confirm `cluster_coherence` stub is still live and no silent behavior change; verify bucket threshold constants are consistent with `src/llm/router.py` thresholds — `router.py` uses 0.75/0.45, check scoring.yaml still matches)
5. `src/config/scoring.yaml` + `src/config/settings.py` (changed — T34 adds `CHEAP_MODEL`, `MID_MODEL`, `STRONG_MODEL` env vars; verify YAML weight sum invariant still holds and new env var defaults are safe if unset)
6. `src/bot/handlers.py` (changed — T32: verify `generate_recommendations` import at line 15 is now dead code since `handle_run_digest` no longer calls it; dead import may mask future confusion about delivery ownership)
7. `docs/spec.md` section 11 (regression check — ARCH-5: spot-check T27 variable rename alignment)

---

## Cycle Type

Targeted — no new phase boundary crossed. T29–T34 are fix and infrastructure tasks closing Cycle 2 stop-ship findings, plus one early Phase 3 scaffolding task (T34 router). The architectural model has not changed; the delivery pipeline is stabilized. The Phase 1 baseline documentation deliverables remain the primary outstanding gap. A full cycle is not warranted until Phase 1 is declared complete and Phase 2 begins.

---

## Notes for PROMPT_3

1. **Phase 1 gate is the consolidation focus**: The project has transitioned to Roadmap v2 but Phase 1 success criteria are not satisfied. PROMPT_3 should produce a clear statement of what is still required for Phase 1 exit: minimum doc updates (architecture.md, spec.md section 11), baseline run artifact, and quality_metrics schema documentation. This is the single highest-priority output for this cycle.

2. **Router partial wiring (ARCH-NEW-1)**: T34 is technically Phase 3 work introduced during Phase 1. PROMPT_3 should make a definitive call: either label it as pre-wiring scaffolding acceptable under Phase 1 scope, or flag it as a scope violation requiring a Phase 3 gate. Either way, the finding needs resolution before the next Orchestrator session.

3. **CODE-5 and CODE-7 carry-forward**: Both have been open since Cycle 1/2 with no fix. PROMPT_3 should recommend either a concrete fix packet (one-liner sleep, scoring.yaml comment clarification) or explicit deferral with a designated phase target (CODE-5 → Phase 4 delivery contract; CODE-7 → Phase 2 scoring foundation).

4. **Dead import in handlers.py**: If `generate_recommendations` at line 15 of `handlers.py` is no longer called from that module, PROMPT_3 should flag it as cleanup debt (confusing delivery ownership, potential re-introduction of CODE-6 pattern).

5. **Baseline test count**: Cycle 3 baseline is 44 passing tests. PROMPT_3 must confirm this as the locked baseline and note it as the entry state for Phase 1 completion verification.
---
