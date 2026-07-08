# Hermes / Personal Intelligence Assistant Roadmap

Status: planning roadmap
Created: 2026-07-08
Owner: private single-user operator workflow

## Why This Phase Exists

KIR-Q0..KIR-Q13 are marked implemented in this repo. The system now has a
curated intelligence pipeline: Telegram archive, Knowledge Atoms, Idea Threads,
frontier analysis, Weekly AI Intelligence Workbook, MVP Radar section,
feedback, Strategy Reviewer, and generated Obsidian projection.

The next phase is not another report feature. The next phase is convenience and
usefulness:

```text
Telegram posts
  -> durable archive
  -> Knowledge Atoms
  -> Idea Threads
  -> Frontier Analysis
  -> Weekly AI Intelligence Workbook
  -> Project Implementation suggestions
  -> MVP Radar conservative validation
  -> generated Obsidian projection
  -> reactions + voice feedback
  -> Strategy Reviewer suggestions
  -> Hermes concierge
  -> PI Assistant / curated retrieval Q&A
  -> human-approved Codex tasks
```

The product works only if each week the operator can say:

1. I understood X.
2. I checked Y.
3. I improved project Z.
4. I decided not to do W.

Beautiful reports are not enough. The four-week dogfood test must prove that
the system changes decisions and actions without becoming another workload.

## Current Repo Verification

Docs and code reviewed on 2026-07-08 show KIR-Q0..KIR-Q13 documented as
implemented. The implementation surfaces exist for KIR provenance, KIR-backed
Radar gates, simplified reaction feedback, confirmed text/voice feedback
intake, feedback-aware reports, Weekly AI Intelligence Workbook, Deep
Explanation Cards, diagrams, Project Implementation, MVP Radar section,
Strategy Reviewer, quote/claim evidence hardening, and Obsidian projection.

Caveats:

- KIR-Q-008 standard loop is verified, but forced frontier regeneration remains
  blocked without `LLM_API_KEY` or `ANTHROPIC_API_KEY`.
- KIR-Q-009 is intentionally deferred until 3-4 stable weekly runs.
- Telegram reaction visibility and deployed inline callbacks still need live
  operator validation.
- User value is not proven until the four-week dogfood protocol is completed.

## Product Roles

### Hermes

Hermes v0.1 is a Telegram-facing operator concierge / chief-of-staff.

Hermes routes, summarizes, reminds, confirms, and prepares tasks. Hermes does
not decide truth.

Hermes should answer:

- What should I do this week?
- What is the main point of the workbook?
- Explain this strong signal.
- What project actions are suggested?
- What does MVP Radar say and why?
- What feedback did I leave?
- What did the Strategy Reviewer suggest?
- Prepare a Codex task for this improvement.

Hermes can:

- summarize workbook status;
- call PI Assistant over curated intelligence items;
- collect feedback text/transcripts;
- show Strategy Reviewer suggestions;
- prepare Codex prompt text for manual approval.

Hermes must not:

- edit code;
- edit YAML configs;
- run Codex;
- mark an MVP as build-ready;
- delete memory;
- weaken evidence gates;
- treat no reaction as negative;
- become an independent source-of-truth memory.

### PI Assistant

PI Assistant is a bounded conversational/RAG interface over curated
intelligence objects.

It answers questions about reports, claims, threads, projects, MVP status, and
feedback. It must cite source refs, atom IDs, thread slugs, workbook sections,
or Radar dossier IDs when making source-grounded claims.

PI Assistant must separate:

- source-grounded claims from curated intelligence objects;
- general background explanation from model knowledge;
- insufficient evidence from weak-but-present evidence.

PI Assistant must not:

- run broad raw Telegram RAG by default;
- become a second source of truth;
- edit code/config/profile/projects;
- write feedback without confirmation;
- weaken Radar/evidence gates.

### Strategy Reviewer

Strategy Reviewer remains an advisory layer after feedback or on demand.

It should produce:

1. What I learned about your taste this week.
2. What to keep.
3. What to demote.
4. What to test next week.
5. Suggested memory updates.
6. Suggested config changes requiring approval.
7. Suggested Codex tasks.
8. Risks / do not change.

Strategy Reviewer may suggest Codex-ready tasks, but it must not modify
code/config itself.

## Dream Motif Interpreter Pattern Review

Reference repo:

```text
/srv/openclaw-you/workspace/Dream_Motif_Interpreter
```

Files reviewed:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/TELEGRAM_INTERACTION_MODEL.md`
- `app/assistant/chat.py`
- `app/assistant/facade.py`
- `app/assistant/tools.py`
- `app/assistant/prompts.py`
- `app/retrieval/query.py`

Adopt now:

- Telegram is an interface layer, not source of truth.
- Assistant calls a bounded facade/tool catalog instead of raw DB sessions.
- Tool loop is bounded and should return insufficient evidence when needed.
- Voice messages become transcripts and enter the same assistant path.
- Session history is interaction state, not archive memory.
- Mutations require confirmation, audit, and explicit verification.
- The facade returns DTO-like dict/list shapes, not ORM rows or raw
  connections.

Defer:

- Vector retrieval until scoped curated retrieval proves insufficient.
- Rich chat curation tools until the feedback confirmation loop is stable.
- Cross-surface UI such as Mini App style flows.

Reject:

- Domain-specific dream interpretation logic.
- Postgres/pgvector as a P0 dependency.
- Raw archive RAG over all Telegram posts.
- Uncontrolled mutation tools in the assistant loop.

## Hermes Guide Review

Hermes Guide is community documentation, not an authoritative product contract.
Patterns below were evaluated from:

- https://hermesguide.xyz/wiki/
- https://hermesguide.xyz/wiki/gateway-setup/
- https://hermesguide.xyz/wiki/memory-systems/
- https://hermesguide.xyz/wiki/profiles-multi-agent/
- https://hermesguide.xyz/wiki/coding-agent/
- https://hermesguide.xyz/wiki/best-practices/

### Adopt Now

- Telegram gateway / operator concierge pattern. The gateway setup page frames
  Telegram as a practical primary messaging interface and recommends separating
  chats/groups/topics for focused sessions.
- Short session-oriented commands. This maps cleanly to `/weekly`, `/actions`,
  `/explain`, `/projects`, `/mvp`, `/feedback`, `/strategy`, and `/codex`.
- Dedicated Hermes role/profile description. A SOUL.md-style role is useful as
  a prompt/profile contract even if only one Hermes profile exists in v0.1.
- Plan -> confirm -> execute boundary. Hermes should prepare actions and ask
  for confirmation before writes.
- Verification after writes. The memory systems page explicitly calls out the
  failure mode where an agent claims it wrote something but no file changed.
- Cost/session hygiene. Keep conversations focused and short; do not leave
  long-running context as hidden product state.

### Defer Until After Four-Week Dogfood

- Multiple Hermes profiles. The profiles page treats profiles as separate
  stateful agents, not lightweight presets; this is too much for v0.1.
- External memory providers such as Hindsight, Honcho, MemPalace, OpenViking,
  Graphiti, Hippo, or similar. They may be useful later, but they create memory
  bloat and source-of-truth risk now.
- Email, WhatsApp, Discord, or additional gateways.
- Complex cross-profile communication and profile orchestration.
- Hermes coding automation. Hermes may prepare Codex prompts, but it must not
  run Codex automatically.
- Community/upcoming workflow features such as topic-to-profile routing or
  Kanban-style orchestration until they are proven useful and stable.

### Reject For This Project

- Hermes as source of truth.
- Hermes memory replacing SQLite, Workbook JSON/HTML, feedback logs, Radar
  dossiers, Strategy Reviewer notes, or generated Obsidian projection.
- Autonomous profile/config/code changes.
- Raw Telegram RAG through Hermes memory.
- Multi-user Hermes setup.
- Gateway fragmentation that makes the private workflow noisier.

## Architecture

Hermes and PI Assistant sit above the existing system:

```text
Telegram owner chat
  -> Hermes operator concierge
  -> bounded PI tools
  -> PersonalIntelligenceFacade
  -> curated intelligence retrieval items
  -> authoritative local stores
```

Authoritative stores remain:

- raw post archive;
- Knowledge Atoms;
- Idea Threads;
- claim cards;
- Workbook JSON/HTML;
- feedback logs and feedback intakes;
- Radar dossiers;
- Strategy Reviewer notes;
- generated Obsidian projection.

Hermes never decides truth. Truth comes from curated data objects and their
evidence/provenance.

## Telegram UX

P0 command set:

- `/weekly` - show current workbook status and three main conclusions.
- `/actions` - show one to three actions for the week.
- `/explain` - explain selected signal or ask what to explain.
- `/projects` - show project actions and watch items.
- `/mvp` - show MVP Radar candidate status and why build/focused_experiment is
  or is not allowed.
- `/feedback` - start text or voice feedback intake.
- `/strategy` - show Strategy Reviewer suggestions.
- `/codex` - show prepared Codex task suggestions.

Message style:

- short;
- action-oriented;
- not a wall of text;
- link/open workbook document;
- ask for confirmation before writes.

## Curated Intelligence Retrieval Layer

Do not implement raw RAG over all Telegram posts.

Define a derived retrieval projection:

```text
intelligence_retrieval_items
```

Suggested fields:

- `id`
- `item_type`
  - `workbook_section`
  - `claim_card`
  - `knowledge_atom`
  - `idea_thread`
  - `thread_delta`
  - `action_card`
  - `project_diagnostic`
  - `feedback_event`
  - `mvp_dossier`
  - `strategy_reviewer_note`
- `week_label`
- `title`
- `text`
- `summary`
- `source_refs_json`
- `atom_ids_json`
- `thread_slug`
- `project_name`
- `confidence`
- `evidence_tier`
- `verification_status`
- `status`
- `created_at`
- `updated_at`

P0 retrieval:

- SQLite/FTS or deterministic search over curated items;
- filter before broad search by week, project, thread, item type, and status;
- return insufficient evidence when no strong result exists.

P1 retrieval:

- better ranking over curated item types;
- query expansion from known thread/project names;
- source reference formatting for Telegram answers.

P2 optional:

- vector retrieval over curated items only;
- no vector store over the raw Telegram firehose until curated retrieval proves
  insufficient.

Raw posts are provenance/evidence fallback, not primary answer memory.

## Personal Intelligence Facade

Before Hermes/PI tools, add a bounded read-only facade.

Suggested future files:

- `src/assistant/pi_facade.py`
- `src/assistant/pi_tools.py`
- `src/assistant/pi_chat.py`
- `src/assistant/pi_prompts.py`
- `src/output/intelligence_retrieval_items.py`
- `tests/test_pi_facade.py`
- `tests/test_intelligence_retrieval_items.py`

`PersonalIntelligenceFacade` should expose DTO-like read-only methods:

- `get_current_week_label()`
- `get_workbook_summary(week_label=None)`
- `get_workbook_sections(week_label)`
- `get_idea_thread(slug)`
- `search_idea_threads(query, week_label=None, limit=10)`
- `search_intelligence_items(query, filters=None, limit=10)`
- `get_project_actions(week_label=None)`
- `get_project_diagnostic(project_name, week_label=None)`
- `get_mvp_radar_status(week_label=None)`
- `get_feedback_summary(week_label=None)`
- `list_marked_posts(week_label=None)`
- `get_strategy_reviewer_note(week_label=None)`

Feedback write methods must be separate and confirmation-gated:

- `create_feedback_proposal(transcript_or_text)`
- `confirm_feedback_proposal(proposal_id)`
- `cancel_feedback_proposal(proposal_id)`

No direct raw DB session, sqlite connection, or ORM row should be exposed to
the assistant loop.

## Voice Feedback Integration

Voice feedback should use the Hermes/PI path:

```text
Telegram voice
  -> STT transcription
  -> PI feedback parser
  -> structured proposal
  -> Hermes confirmation message
  -> on confirm: write feedback events/editorial memory/decision journal
  -> Strategy Reviewer uses it
```

Structured feedback proposal fields:

- `useful_items`
- `wrong_priority_items`
- `not_interested_items`
- `too_shallow_items`
- `tried_items`
- `applied_to_project_items`
- `missed_important_posts`
- `project_corrections`
- `source_trust_up`
- `source_trust_down`
- `preference_suggestions`
- `codex_task_suggestions`
- `memory_only_updates`
- `config_change_suggestions`
- `code_change_suggestions`

Confirmation message should show:

- what will be written to memory;
- what is only a suggestion;
- what requires Codex/manual approval.

No confirmed feedback means no memory writes.

## Reaction Integration

The operator should not need to remember emoji semantics.

Rule:

- any visible operator reaction means the post was interesting for some reason;
- raw reaction emoji is kept for audit;
- no reaction means unknown, not negative.

Later classification may infer and confirm whether the interest was technical,
cultural, strategic, project-related, market/MVP, read-later, or try-in-project.
Do not make this classification complex in P0.

## MVP Radar Boundary

MVP Radar is a conservative opportunity scout:

```text
Is there a real MVP opportunity here, validated beyond Telegram?
```

Hermes may summarize Radar status, source mix, missing evidence, next
experiment, and kill criteria. Hermes must not override Radar gates or recast
an `investigate` candidate as build-ready.

## Four-Week Dogfood Overview

Dogfood goal:

Validate whether the system is convenient and useful, not whether more features
can be added.

Weekly loop:

1. Generate workbook.
2. Hermes sends short weekly summary.
3. Operator reads Decision Brief, two Deep Explanation cards, Project Actions,
   and MVP Radar section.
4. Operator completes one read/try/project/MVP validation/reject-defer action.
5. Operator sends voice feedback.
6. Hermes returns parsed summary.
7. Operator confirms.
8. Strategy Reviewer suggests improvements.
9. Operator optionally runs one Codex task.

Detailed dogfood protocol lives in `docs/dogfood_4_week_plan.md`.

## HPI Task Plan

### P0

- HPI-0 - Document Hermes/PI Assistant roadmap and dogfood plan. Implemented.
- HPI-1 - Implement `PersonalIntelligenceFacade` read-only contract. Implemented.
- HPI-2-lite - Build deterministic curated `intelligence_retrieval_items`
  projection. Implemented as SQLite-first/read-only in-memory projection.
- HPI-3 - Define PI Assistant bounded tool catalog. Implemented.
- HPI-8 - Track four-week dogfood metrics and weekly review artifact.
  Implemented as compact private artifact helper.

### P1

- HPI-4 - Telegram Hermes concierge commands. Implemented.
- HPI-5 - Route voice feedback through PI/Hermes confirmation loop.
  Implemented via confirmation-gated feedback intake.
- HPI-6 - Deliver Strategy Reviewer summaries through Telegram. Implemented.
- HPI-7 - Add workbook action-status and feedback follow-up loop.
  Implemented as read-only status projection.

### P2

- HPI-9 - Optional scoped vector retrieval over curated items only. Deferred
  until dogfood proves deterministic search insufficient.
- HPI-10 - Post-dogfood product decision review. Blocked until four dogfood
  weeks are recorded.

## Acceptance Criteria

HPI phase acceptance:

- docs explain Hermes, PI Assistant, Strategy Reviewer, and dogfood boundaries;
- HPI task queue exists with acceptance criteria and stop conditions;
- first implementation task is small and Codex-ready;
- no code/config mutation is delegated to Hermes;
- no raw Telegram firehose RAG is introduced;
- no new source of truth competes with SQLite/workbook/Radar/Obsidian
  projection;
- four-week dogfood metrics can be collected before adding complex features.

## Implementation Note - 2026-07-08

HPI-1 through HPI-8 are implemented as a safe dogfood foundation:

- `PersonalIntelligenceFacade` exists and returns stable DTO-like dictionaries
  and lists for curated workbook, thread, project, MVP, feedback, marked-post,
  and retrieval reads.
- `intelligence_retrieval_items` builds a deterministic curated projection from
  workbook sidecars, claim cards, Knowledge Atoms, Idea Threads, project
  diagnostics/actions, MVP Radar status, feedback summaries, and Strategy
  Reviewer advisory notes when those sources are available.
- No mutation tools were added.
- No raw Telegram firehose RAG or vector search was added.
- `pi_tools` defines a bounded read-only tool catalog with evidence summaries
  and explicit insufficient-evidence states for future PI/Hermes calls.
- Hermes commands now expose weekly summary, actions, curated explanation,
  projects, MVP status, Strategy Reviewer notes, and Codex prompt drafts
  without executing mutation tools.
- Voice/text feedback remains confirmation-gated.
- Action statuses are projected from confirmed feedback; no feedback remains
  `unknown`.
- Dogfood review helpers can write compact private weekly JSON/Markdown
  artifacts and summarize four weeks.
- The next recommended step is operational: run dogfood week 1, collect metrics,
  and do not implement HPI-9 unless deterministic curated search fails in real
  use.

## Operational Setup Note - 2026-07-08

The VPS production baseline is configured for dogfood:

- Hermes runs through `telegram-bot.service` as a Telegram command concierge
  and bounded LLM chat. Plain text, `/chat`, `/hermes`, and `/ask` route to a
  PI tool loop where the model may call only read-only curated-intelligence
  tools.
- Weekly ingestion, digest delivery, MVP Radar delivery, cleanup, and study
  reminders run through systemd timers.
- `scripts/healthcheck.sh` is the primary readiness check for DB/config/output
  ownership and weekly delivery state.
- `ops-validate` distinguishes infrastructure readiness from live feedback
  evidence; `needs_live_event` means a real Telegram reaction or inline
  callback still needs to be observed.

This does not change HPI safety scope:

- no raw Telegram firehose RAG is enabled;
- no vector retrieval is enabled;
- no mutation tools or autonomous Codex execution are enabled.

Dogfood week 1 should validate the bounded chat, command concierge, workbook
reading loop, reaction sync, feedback confirmation, Strategy Reviewer summary,
and dogfood metric artifact before any HPI-9 work.

## Risks

- Hermes becomes a competing brain instead of router.
- PI Assistant answers from raw model knowledge instead of curated evidence.
- RAG over raw posts creates noise or hallucinated continuity.
- Hermes memory replaces authoritative SQLite/Workbook/Obsidian projection.
- Workbook becomes too long to read.
- Voice feedback overfits to one mood/week.
- Strategy Reviewer creates too many Codex tasks.
- Assistant mutation tools become unsafe.
- Obsidian note explosion.
- Passing tests is mistaken for user value.
- Four-week dogfood is skipped and the system keeps growing without validation.
- Hermes Guide patterns are copied blindly and add complexity.
- Multi-profile Hermes setup is introduced too early.
- Messaging gateway fragmentation makes UX worse.

## Stop Conditions

Stop and ask the operator if a task:

- adds autonomous code/config editing;
- weakens evidence gates;
- treats no reaction as negative;
- makes Radar build from Telegram-only evidence;
- creates a public/multi-user product;
- adds raw-post vector RAG as default;
- commits private generated reports;
- adds visual polish before feedback/action usefulness;
- turns Hermes into source of truth;
- introduces Hermes external memory as authoritative store.

## Next Operational Task

Run HPI dogfood week 1 and collect the weekly dogfood metrics.

Scope:

- generate or locate the weekly workbook;
- use Hermes `/weekly`, `/actions`, `/mvp`, and `/strategy`;
- complete at least one real read/try/project/MVP reject-defer action;
- send and confirm voice/text feedback;
- record HPI-8 dogfood metrics and keep generated artifacts private.

Do not implement vector retrieval, multi-profile Hermes, external Hermes
memory, or mutation tools before dogfood evidence justifies them.
