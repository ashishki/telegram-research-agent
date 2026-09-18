# Codex Handoff

Status: active
Last updated: 2026-09-17

## Product Direction

The current planned workstream is one personal Telegram assistant for archive
research, controlled public verification and topic news digests. UTD remains a
specific watch scenario. The owner requested registration of this implementation
queue on 2026-09-17; this does not start implementation or authorize live jobs.
See `docs/adr/ADR-009-personal-search-and-news.md` and the `PRM-SN` tasks in
`docs/tasks.md`. The owner clarified that the launch prompt must pursue one
end-to-end implementation goal. When assigned, it covers all twelve PRM-SN
tasks and engineering gates DR-1 through DR-5, starting at the first unfinished
task; registration alone still does not start it.

Use `docs/CODEX_PROMPT.md` for current scope and
`docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md` for phase review gates. Implement directly;
an independently invoked `codex exec` reviewer is read-only, uses
`gpt-5.6-terra` with `high` reasoning, and cannot approve human/runtime gates.
Record observed model/effort, not only requested flags. Do not start a reviewer
or implementation merely because the task is listed as planned.

## Historical Implementation Context

The following dated recap is historical context, not proof of today's effective
runtime flags, archive freshness, profile confirmation or service health. Verify
active call paths when relevant; the audit baseline is
`docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md`.

The repository is being retrofitted from a weekly-report-centered Telegram
intelligence system into Personal Telegram Research Memory + Grounded Assistant.
HEAD contains corrective PRM implementation slices through PRM-7 and PRM-9
through PRM-13, including bounded SQLite FTS archive search, a grounded
assistant vertical slice, deterministic external-verification requirement
routing, confirmation-gated saved memory proposals, and a deterministic
Knowledge Library topic-page renderer. HEAD also contains PRM-14 deterministic
project context and decision-support routing, PRM-15 corrected learning-state
projection/migration semantics, and PRM-16 deterministic Weekly Brief V3
projection with legacy Brief/Atlas demotion semantics. HEAD also contains
PRM-17 deterministic runtime workflow contracts and privacy-safe aggregate
telemetry receipts. The PRM-13 through PRM-17 batched deep review is recorded.
PRM-18 deterministic release/dogfood gate is implemented. The current
post-PRM28 receipt records deterministic local no-vector RAG readiness but
still blocks dogfood because explicit human dogfood-start approval is missing.
PRM-18A Operator LLM
Chat UX Contract,
PRM-18B LLM-backed memory chat CLI, and PRM-18C Telegram `prm-assistant` UX
parity/runbook are implemented; the PRM-18A through PRM-18C batched deep review
is recorded. The polished project-aware research-session assistant target is
documented by PRM-21. PRM-22 implements a fixture-first linked-source
resolver/cache, and PRM-23 implements a bounded fixture-first `memory research`
planner/CLI with no live fetch, provider call, service start, dogfood evidence,
durable production write/cache, or vector/backend approval. PRM-24 now has a
50-row operator-approved generated seed gold set and a privacy-safe SQLite FTS
baseline report; the labels are not independent human review evidence. PRM-26
accepted the no-vector path for now under
`operator-approval-2026-08-11-no-vector-prm28-path`, and PRM-28 implements the
no-vector answer gate over SQLite FTS/context pack. PRM-27 was later approved
and implemented as a local SQLite vector sidecar under
`operator-approval-2026-08-11-full-stack-local-vector-telegram-llm` and
`docs/adr/ADR-004-prm27-local-vector-sidecar.md`: no external embeddings, no
hosted vector service, no canonical DB mutation, no live web research, no
production migrations, and no dogfood start. A later 2026-08-11 operator
instruction approved enabling the local vector/RAG/LLM/Telegram stack for
manual user testing: the gitignored local vector sidecar was built, PRM hybrid
retrieval and Telegram LLM/router flags were set in the host `.env`, and
`telegram-prm-assistant.service` was installed, enabled, and started. This is a
manual runtime test state only, not PRM-19 dogfood evidence. The current
post-PRM28 gate receipt is
`evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`; it leaves
`dogfood_started=false` and `release_claimed=false`. PRM-24 through PRM-28
formalize the required full product RAG path before dogfood: gold eval set,
citation-safe context pack,
hybrid/vector ADR and privacy budget, approved retrieval implementation, and
product chat acceptance gate. A post-PRM28 local UX trial is recorded at
`docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md`: no-vector RAG is technically
usable for local archive discovery. A follow-up safe UX polish adds compact
default `memory research` rendering, `--debug` audit rendering, Russian heading
localization, freshness-first current-fact boundaries, local path redaction,
narrow repo-context cues, and no drafts for current-fact freshness-boundary
answers. A subsequent safe Telegram UX polish adds ordinary-message auto
routing, local-only `/brief` source-backed editor briefs, volatile per-chat
mode-aware follow-up context, deterministic AI-transformation query hints, and
a corrected archive-scoped-vs-current-price answer gate. Remaining UX gaps are
deeper multi-turn product memory and curated-memory relevance/deduplication.
PRM-8 remains historical/conditional outside the approved PRM-27 local sidecar
scope. PRM-19 and PRM-20 are
not started; PRM-19 requires explicit human dogfood-start approval before it
can start and real four-week operator dogfood evidence before it can complete.
PRM-20 requires PRM-19 evidence plus explicit compatibility archive/delete/move
approval. The old live
Telegram bot and
Report V2 weekly timer were stopped and disabled on 2026-07-29; see
`docs/PRODUCT_OPERATING_MODEL.md` and
`docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md`. A dedicated safe
`prm-assistant` runtime entrypoint and repo unit template exist. As of
2026-08-11 18:27 CEST the unit is installed, enabled, and running for manual
operator testing only; it is not dogfood evidence and the safe entrypoint does
not run automatic startup migrations. The `prm-assistant` runtime routes
ordinary text and voice transcripts through
`/auto`: deterministic safe routing chooses local research or local editor
briefs by default, while LLM auto-routing and auto chat require both
`PRM_TELEGRAM_AUTO_LLM_ROUTER=1` and
`PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`. Telegram research/brief can add
bounded LLM synthesis only after local hybrid RAG has run when
`PRM_TELEGRAM_RAG_LLM_SYNTHESIS=1` is also set; the synthesis receives bounded
cited snippets, not the raw corpus, and usage recording is suppressed to avoid
production DB writes. Telegram research/brief messages are report views:
topical sections, sources, and plain-language boundaries, but no visible
technical metrics/cost/tool-call/debug footer. Manual `/research <question>`,
`/brief <question>`, and separately gated `/chat` remain fallback commands.
A local user-facing `memory ask` command exists for immediate local evidence
questions without LLM calls, external search, service starts, migrations, or
writes.
On 2026-08-12 a bounded manual PRM archive refresh was added and run after
operator instruction. `memory refresh-archive --days 21
--confirm-canonical-write` refreshed the canonical local Telegram archive from
3,709 to 4,166 rows, advanced max `posts.posted_at` to
2026-08-11T21:47:37+00:00, rebuilt the approved local gitignored vector
sidecar, and is recorded at
`docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md`. This was a canonical
local DB write for manual testing only, not PRM-19 dogfood evidence. The command
avoids legacy services/timers, migrations, reaction sync, media download,
vision LLM, provider egress, source-event writes, report generation, dogfood
start, and release claims.
On 2026-08-12 the operator then approved a once-weekly timer for this same
bounded archive-refresh path. `telegram-prm-archive-refresh.timer` runs
`telegram-prm-archive-refresh.service` weekly on Monday 08:10 Europe/Berlin,
using `memory refresh-archive --days 21 --confirm-canonical-write --json`.
The timer is not a legacy ingest/report timer, not PRM-19 dogfood evidence, and
must preserve the same safety boundary: no migrations, reaction sync, media
download, vision LLM, provider egress, source-event writes, report generation,
external embeddings, hosted vector service, release claim, or dogfood start.

## Operating Rules

- Work directly in this repository; do not spawn nested Codex CLI processes for
  bootstrap or implementation.
- Do not run live Telegram ingestion, reaction sync, Radar, Frontier, report
  generation, full archive LLM backfill, external embeddings, hosted vector
  services, or external web research jobs unless a task explicitly authorizes
  it. PRM-27 local vector sidecar indexing is authorized only inside ADR-004.
- Do not modify production database contents.
- Do not commit private Telegram data or generated private reports.
- Do not enable external skills without approved trust records.
- Human operator is final completion authority.

## Canonical Docs

- docs/CODEX_PROMPT.md
- docs/tasks.md
- docs/PROJECT_BRIEF.md
- docs/ARCHITECTURE.md
- docs/IMPLEMENTATION_CONTRACT.md
- docs/personal_research_memory_product_contract.md
- docs/final_acceptance_plan.md
- docs/PRIVACY_THREAT_MODEL.md
- docs/COST_BUDGET.md

## Current Next Task

Use `docs/prompts/prm_search_news_implementer.md` for one end-to-end goal:
all twelve PRM-SN tasks, independent phase reviews and corrections, integrated
local verification, and a concrete pilot packet. Start with PRM-SN-1A if still
unimplemented. Under that assigned goal, continue after each passed engineering
gate without asking permission for the next already-assigned phase. Do not stop
at one card or one review. Immediate safety triggers apply inside phases.
Existing RFX/UTD statuses and human/runtime gates remain separate.

The 2026-09-03 receipt records bounded UTD timer enablement pending profile
confirmation. Its current service/profile state was not observed by the
2026-09-17 audit. Preserve those scoped permissions; this queue does not widen
sources, notifications or autonomy. PRM-19 and PRM-20 still require their
separate human approvals/evidence. Do not start legacy timers or claim release.
