# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-07-06

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

Detailed next-roadmap context lives in
`docs/next_development_roadmap.md`.

Reader-facing report quality and Demand-to-MVP Radar handoff details live in
`docs/report_quality_roadmap.md`.

Pathway live source intelligence and Radar incremental-indexing work lives in
`docs/pathway_live_source_intelligence.md`.

AI Knowledge Intelligence Desk strategy, architecture, phases, and implementation
details live in `docs/ai_knowledge_intelligence_roadmap.md`.

## Current State

Implemented:

- Telegram ingestion and normalized post storage
- deterministic scoring and project relevance
- reaction-based feedback sync for original Telegram posts
- inline Telegram feedback cards for implementation ideas
- compact Implementation Ideas feedback cards capped for Telegram scanning
- integration-style bot polling callback dispatch test around `bot.run_bot`
- weekly Research Brief, Implementation Ideas, and Study Plan
- README and active docs aligned with current delivery/feedback behavior
- evidence memory via `signal_evidence_items`
- Implementation Ideas evidence guard: parsed `[Implement]` / `[Build]` ideas without concrete source post URLs render an insufficient-evidence note instead of actionable recommendations
- decision continuity via `decision_journal`
- operator-authored weekly usefulness logs via `weekly_usefulness_logs`
- project context snapshots
- low-signal / empty digest health alerts
- weekly quality trend from Research Brief receipt health alerts in `score-stats`
- monthly `projects.yaml` review guardrail in `health-check`
- memory inspection CLI
- Telegram Channel Intelligence design, schema migrations, deterministic repeated-claim extraction, canonical source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface captured in `docs/telegram_channel_intelligence.md`
- Research Brief receipt SQLite schema, storage helpers, generation-time creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes via `research_brief_receipts`
- Core-compatible Research Brief receipt adapter, weekly audit-note hash wiring,
  `memory inspect-core-receipt` for delivered briefs, and deterministic Core
  evidence lookup checks via `--verify-evidence`
- Core receipt schema compatibility tests and product-local boundary guards
- artifact-level operator feedback via `log-artifact-feedback` and
  `memory inspect-artifact-feedback`
- monthly operator report via `operator-report`
- source down-rank explanations via `memory explain-source-downrank`
- product split gate via `product-split-gate`
- production validation surfaces for reaction sync and inline callbacks via
  `ops-validate`
- deterministic report-quality gates for weekly artifacts via
  `output.report_quality`, digest delivery warnings, Study Plan/Project
  Insights logging, and `operator-report`
- reader-facing Research Brief Decision Brief and Actions header, with early
  What Changed summary and compact Telegram notification funnel/action count
- artifact-level Telegram feedback buttons for Research Brief,
  Implementation Ideas, MVP weekly, and Study Plan delivery notifications,
  recorded in `artifact_feedback_logs`
- reader-facing Research Brief evidence/source-mix summary derived from local
  receipt evidence lookup, source links, fallback state, and top channels
- Demand-to-MVP Radar final gate contradiction guard: runtime LLM Markdown
  cannot override deterministic source-mix gates, and Radar Markdown/JSON agree
- Demand-to-MVP Radar Candidate Dossier output: canonical
  `build/focused_experiment/investigate/reject` status, decision, confidence,
  next action, missing evidence, next experiment, kill criteria, and Telegram
  notification status display
- Demand-to-MVP Radar source-mix truth surface: selected-candidate source mix
  in Markdown/JSON, missing credentials, Reddit API vs SERP-indexed Reddit, and
  GitHub primary/repeated-variant labeling surfaced to Telegram notification
- Demand-to-MVP Radar report-quality tests: Candidate Dossier top block,
  required sections, source-mix card, missing evidence, kill criteria,
  existing-project context, and no contradictory build-ready claims
- internal LLM cost guardrail sentinel via deterministic `llm_usage` summaries:
  budget/spike warnings in `cost-stats` and monthly `operator-report`
- weekly artifact consistency contract: Study Plan/Project Insights checks
  against Research Brief facts, MVP delivery build-readiness guard, and
  operator-report consistency warnings
- weekly editorial memory via `memory inspect-editorial-memory`: local
  operator/system-authored keep/change/demote/test-next-week notes from
  artifact feedback, usefulness logs, report-quality findings, receipt health,
  and source down-rank explanations
- Pathway-ready live source intelligence: append-only source events from
  Telegram ingestion, deterministic live-source snapshots, Radar context-only
  consumption, and optional `mvp-weekly --with-live-source-index` bridge
- weekly delivery health checks in `health-check`: inactive
  `telegram-digest.timer`, missing current-week digest after the scheduled
  Monday window, root-owned `data/output` files, and deployed
  `scripts/healthcheck.sh` wiring through the Python health surface
- non-blocking best-effort `llm_usage` recording: short SQLite busy timeout,
  autocommit insert, closed usage connection, and quiet skip under database
  lock contention so report generation is not delayed by cost logging
- Knowledge Atom schema and storage helpers: `knowledge_extraction_batches`
  and `knowledge_atoms` migrations with source citation JSON, atom type,
  confidence/novelty/utility/relevance scores, staleness status, stable keys,
  and focused round-trip tests
- cheap batched Knowledge Atom extraction CLI via `knowledge-extract`: bounded
  post batches, cheap-model routing, JSON-only validation, idempotent completed
  batch skips, failed-batch recording, source URL derivation, and
  `memory inspect-knowledge-atoms`
- Telegram digest timer was restored on 2026-07-06 after being inactive since
  2026-06-22; 2026-W28 Research Brief and Implementation Ideas were regenerated
  manually. This exposed the next product direction: convert the project from a
  project/MVP-centered weekly digest into an AI Knowledge Intelligence Desk.

## Active Maintenance Queue

The previous receipt/source-trust/operator-reporting backlog, reader-facing
report quality, Radar handoff, cost guardrails, artifact consistency, editorial
memory queue, and initial Pathway-ready live source intelligence work are
implemented.

The active queue is now the AI Knowledge Intelligence Desk roadmap. The goal is
to build a durable knowledge base from Telegram posts, extract cheap structured
knowledge atoms, group them into temporal idea threads, generate a
human-readable weekly HTML AI intelligence report, and project the curated
knowledge layer into Obsidian for long-lived browsing. MVP Radar and project
recommendations become downstream consumers.

| ID | Priority | Task | Notes |
|---|---:|---|---|
| KIR-020 | P2 | Build Idea Thread grouping and momentum layer | Group atoms into evolving ideas, connect sources, compute 7/30/90 day momentum, and mark active/stale/superseded/hype-only statuses. |
| KIR-030 | P3 | Generate standalone weekly AI Intelligence HTML report | Create the new primary report with Executive Brief, What Changed, Idea Evolution, Tools/Models/Practices, Contradictions, Read Queue, Try This Week, Source Map, and Appendix. |
| KIR-035 | P3 | Generate Obsidian knowledge vault projection | Add `obsidian-export` that writes deterministic Markdown notes for weekly intelligence, idea threads, tools/models, practices, channels, read queue, and experiments into a dedicated vault or scoped generated namespace. Raw Telegram posts remain in the database; generated notes must have frontmatter, backlinks, source references, stable slugs, and must not overwrite hand-authored notes. |
| KIR-040 | P4 | Add report feedback and personal learning loop | Capture read/useful/tried/missed/noise feedback and feed it into operator relevance and weekly read/try/build recommendations. |
| KIR-050 | P5 | Rewire MVP Radar and project recommendations as downstream consumers | Feed MVP/project artifacts from knowledge threads instead of raw weekly scoring and keyword-only project matching. |

Implementation details and acceptance criteria for the active queue are in
`docs/ai_knowledge_intelligence_roadmap.md`. Historical report-quality and Radar
paths remain in `docs/report_quality_roadmap.md`.

Production validation remains inspectable with `ops-validate`. If no live
Telegram reaction or callback event has occurred in the selected window, the
command reports `needs_live_event` rather than storing unverified success.

## Parking Lot

- Public/product UI after `PROD-1` passes.
- Referee pass for high-impact claims after source-trust explanations are
  inspectable.
- Productized Telegram Channel Intelligence repo or workspace after repeated
  operator value is demonstrated.
- Pathway as an incremental indexing backend after the deterministic
  knowledge-atom and idea-thread contracts are proven locally.
