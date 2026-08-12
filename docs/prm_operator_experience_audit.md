# PRM Operator Experience Audit

Status: planning evidence, not dogfood
Date: 2026-08-12
Target repository SHA: `82c0c527ffdd797aab716a2d1079cd6849caa208`
Playbook checkout SHA: `965612aa463fca1a35a55104633d0e09da33d615`

## Boundary

This audit is a documentation and planning artifact. It did not implement
product behavior, modify production SQLite data, start or restart systemd
units, change environment variables, run live Telegram ingestion, run reaction
sync, call providers, run live web research, rebuild the vector sidecar,
generate reports, install skills, move/delete compatibility code, start
dogfood, or make release/product-value claims.

No private Telegram post bodies are copied here.

## Repository And Playbook State

Target repository inspection:

- branch: `master`;
- dirty state before this planning edit: clean;
- HEAD: `82c0c527ffdd797aab716a2d1079cd6849caa208`;
- last visible commit: `82c0c52 docs: refresh current project README`.

Playbook repository inspection:

- branch: `master`;
- dirty state: clean;
- HEAD: `965612aa463fca1a35a55104633d0e09da33d615`;
- last visible commit: `965612a docs: document audited execution and governance maturity`.

The target Project Brief still pins Playbook SHA
`5583eca96c4d2d480b5574ed78bea63e0b07ebf0`. That pin is stale relative to the
current Playbook checkout inspected for this planning pass.

## Verified Current Runtime / Product State

| Claim | Classification | Evidence |
| --- | --- | --- |
| Product center is Personal Telegram Research Memory + Grounded Assistant. | verified in docs / product contract, not proven value | `README.md`, `docs/PRODUCT_OPERATING_MODEL.md`, `docs/ARCHITECTURE.md`, `docs/personal_research_memory_product_contract.md` |
| Retained Telegram archive is searchable through SQLite FTS. | verified in code and local read-only aggregate check | `src/db/archive_search.py`, `tests/test_archive_search.py`, read-only counts: `raw_posts=4166`, `posts=4166`, `posts_fts=4166`, FTS drift `0/0` |
| Local SQLite vector sidecar is available for approved hybrid retrieval. | verified in code, deterministic tests, and local runtime file state | `src/db/archive_vector.py`, `tests/test_archive_vector.py`, `docs/adr/ADR-004-prm27-local-vector-sidecar.md`, local sidecar exists at gitignored `data/vector/archive_vector.sqlite` |
| `telegram-prm-assistant.service` is active for manual operator testing. | verified by local runtime receipt; not rechecked with systemctl in this session | `docs/audit/PRM_MANUAL_TELEGRAM_ASSISTANT_ACTIVATION_2026-08-11.md`, `systemd/telegram-prm-assistant.service` |
| Normal text and voice transcripts enter the PRM auto route. | verified in code and committed tests | `src/bot/handlers.py`, `tests/test_callbacks.py`, `tests/test_handlers.py` |
| `/research` and `/brief` return source-backed packaged reports. | verified in code and committed tests; quality still unproven by dogfood | `src/bot/handlers.py`, `src/assistant/memory_research.py`, `tests/test_handlers.py`, `docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md` |
| `/chat` and model-based routing are provider-egress gated. | verified in code and committed tests | `src/bot/handlers.py`, `src/main.py`, `tests/test_handlers.py`, `tests/test_cli.py`, `docs/PRIVACY_THREAT_MODEL.md` |
| Bounded weekly archive-refresh timer is installed. | verified by local runtime receipt and unit templates; not rechecked with systemctl in this session | `docs/audit/PRM_WEEKLY_ARCHIVE_REFRESH_TIMER_2026-08-12.md`, `systemd/telegram-prm-archive-refresh.*` |
| Legacy weekly-report automation remains frozen. | verified by runtime-freeze receipt and current operating docs; not rechecked with systemctl in this session | `docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md`, `docs/PRODUCT_OPERATING_MODEL.md` |
| PRM-19 dogfood has not started. | verified by release-gate receipt and docs | `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`, `docs/tasks.md`, `docs/PRODUCT_OPERATING_MODEL.md` |
| Release readiness and public product value are not claimed. | verified by docs and gate receipt | `README.md`, `docs/final_acceptance_plan.md`, `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json` |

## Local-Only UX Probe

Allowed local-only commands were run without `--llm-approved` and without
printing private snippets.

| Probe | Result |
| --- | --- |
| `memory status --json` | status `local_mode_available_gated_product_path`; available local commands `7`; reported no DB read/write, provider egress, or service start |
| `memory ask "какие есть практики по agent evals?"` | intent `concept_search`; answer about 2,975 chars / 23 lines; professional relevance detectable; not decision-first; no next action detected; no local path leak; no provider egress/write |
| `memory ask --project telegram-research-agent "что из последних практик можно применить к проекту?"` | intent `project_application`; answer about 491 chars / 6 lines; decision-first and next action detectable; internal/debug language detectable; no local path leak; no provider egress/write |

Interpretation: local `memory ask` is safe and useful for evidence lookup, but
it does not consistently produce a pleasant, mobile-first, operator-goal-first
answer. The project-specific path can still leak implementation contract
language instead of speaking as a daily assistant.

## Daily-Use Friction

- The operator still sees or can infer too many modes: ordinary message,
  `/research`, `/brief`, `/chat`, `memory ask`, `memory research`, and
  `memory chat`.
- Telegram ordinary messages route through `/auto`, but the mental model is
  not yet contracted as the only normal entrypoint.
- CLI and Telegram answer contracts differ: CLI keeps audit receipts visible;
  Telegram hides more metrics.
- `memory research` is safer and more complete than `memory ask`, but it still
  exposes product-internal vocabulary in CLI mode.
- Save/watch/project/action habits are not yet an inline Telegram loop.
- Reaction sync is not part of the routine archive-refresh path.
- Current/fresh facts are correctly gated locally, but the user still needs a
  clear "verify primary sources" action.

## Command / Mode Confusion

The current implementation contains valuable fallback commands, but the product
should present one default:

```text
normal Telegram text or voice -> PRM auto route -> answer-first response
```

Manual commands should remain as emergency overrides and debugging controls.
The user should not need to know whether a question belongs to research, brief,
chat, memory ask, memory research, or memory chat.

## Response-Quality Findings

Reusable strengths:

- strict freshness parsing exists for date-window questions;
- current external facts are blocked or marked verification-required;
- bounded context packs prevent raw corpus dumps;
- Telegram research/brief strips metrics/cost/tool debug from normal output;
- volatile follow-up context exists for short follow-ups.

Remaining quality gaps:

- answer-first structure is not deterministic across surfaces;
- professional relevance is not a required section;
- project application can be based on descriptor matches without a clear
  portfolio action boundary;
- recommendations are not consistently limited to one bounded next step;
- source citations exist but are not always tied to the exact claim they
  support in the user-facing text;
- no human-usefulness labels prove that real decisions improved.

## Personalization Gaps

Current `src/config/profile.yaml` is primarily topic/source weighting:

- `boost_topics`;
- `downrank_topics`;
- `downrank_sources`;
- `cultural_keywords`.

It does not yet represent:

- professional objective;
- active lens;
- preferred evidence class by lens;
- active project status/priority;
- current skill gap;
- writing/career/product intent;
- expected output form.

Personalization must not reduce raw retrieval recall. It should affect
reranking, framing, and action selection after broad retrieval.

## Project-Context Gaps

Current `src/config/projects.yaml` is a flat list with descriptions, focus
strings, keywords, and exclusions. It lacks explicit:

- `status`;
- `priority`;
- `current_goal`;
- `current_blocker`;
- `next_proof`;
- `preferred_signal_types`;
- `owner_confirmation_status`.

`telegram-research-agent` still includes report-era language such as digest
quality, MVP-of-week bridge, and Radar. That is historically true but no longer
the clean active product descriptor.

Verified local related repositories:

- present: `telegram-research-agent`, `AI_workflow_playbook`,
  `Demand-to-MVP-Radar`, `AI-Rollout-Training-OS`,
  `Workflow-to-Agent-Studio`, `Dream_Motif_Interpreter`;
- absent from current workspace: `Eval-Ground-Truth-Lab`,
  `Agent-Runtime-Grid`;
- `Dream_Motif_Interpreter` has pre-existing local changes and should be
  treated as reference-only for this planning pass.

## Freshness Gaps

The current timer runs Monday 08:10 Europe/Berlin. It is safe for weekly local
archive freshness, but weak for daily current questions and recent tool/model
signals.

Current local aggregate state:

- `raw_posts=4166`;
- `posts=4166`;
- `posts_fts=4166`;
- latest `posts.posted_at=2026-08-11T21:47:37+00:00`;
- FTS/post drift: `0`.

The operator's actual timezone is not independently confirmed in this planning
session. The host/runtime timezone is Europe/Berlin. No timezone or schedule
change should be made without explicit approval.

## Reaction-Loop Gaps

Existing code and receipts support reaction semantics and read-only fast-lane
receipts. However:

- reaction sync is separate from the weekly PRM archive refresh timer;
- reacted posts can be searchable if already in the archive, but the routine
  path does not yet guarantee same-cycle operator feedback visibility;
- failure isolation between archive refresh and reaction sync is not yet a
  routine runtime contract;
- no operator-facing reaction receipt is part of the daily Telegram habit.

Recommended planning direction: keep reaction sync as a separate routine from
archive refresh so Telethon credential/rate-limit failures cannot block archive
freshness.

## Documentation Contradictions / Stale Surfaces

- `README.md` is mostly current but includes operational systemd detail that
  should move to runbooks.
- `docs/README.md` has a stale date and omits the PRM-UX phase.
- `docs/PROJECT_BRIEF.md`, `docs/CODEX_PROMPT.md`, and `docs/tasks.md` still
  pin the older Playbook SHA from the retrofit baseline.
- `docs/operator_workflow.md` starts with PRM local use but quickly re-enters
  long Report V2 / Atlas / Radar routines. The compatibility boundary is not
  visually strong enough.
- `docs/architecture.md` is correctly labelled legacy, but many docs still link
  readers through report-era concepts.
- `src/config/projects.yaml` contains report/Radar-era descriptor language for
  the primary project.

## Current Eval Limitations

- Retrieval and answer-gate evals are deterministic and useful.
- PRM-24 labels are operator-approved generated seed labels, not independent
  human review.
- Existing generation evals test groundedness mechanics, not daily usefulness.
- No real 30-question operator set exists for PRM-19.
- LLM judge output remains advisory until calibrated against operator labels.
- The current release gate is a deterministic readiness classifier, not proof
  that the product helps the operator decide, build, write, or learn.

## Reusable Components For The UX Phase

- SQLite FTS archive search: `src/db/archive_search.py`.
- Local vector sidecar: `src/db/archive_vector.py`.
- Context pack: `src/assistant/rag_context_pack.py`.
- Answer gate: `src/assistant/rag_answer_gate.py`.
- Local research planner/rendering: `src/assistant/memory_research.py`.
- Local ask path: `src/assistant/local_memory_ask.py`.
- Telegram auto/router/rendering: `src/bot/handlers.py`.
- PI tool proposal/confirmation contract: `src/assistant/pi_tools.py`,
  `src/assistant/pi_memory.py`.
- Project context classifier: `src/assistant/project_context.py`.
- Reaction fast-lane receipt: `src/db/reaction_fast_lane.py`.
- Reaction sync implementation: `src/ingestion/reaction_sync.py`.
- Privacy/cost contracts: `docs/PRIVACY_THREAT_MODEL.md`,
  `docs/COST_BUDGET.md`.

## Unresolved Live Questions

1. What timezone should daily freshness follow: operator local timezone,
   Europe/Berlin host time, or a fixed UTC schedule?
2. Should reaction sync be manual, separate timer, or event-driven after the
   first dogfood week?
3. Which professional lenses should be active by default?
4. Which projects are active/priority versus watch/reference?
5. What provider-egress budget is acceptable for manual Telegram synthesis
   during dogfood?
6. Which external verification sources/tools are trusted enough to enable?
7. Which inline actions should be visible in the first Telegram answer:
   save/watch/project/feedback, or a smaller subset?
8. What is the maximum comfortable Telegram answer length for this operator on
   mobile?

