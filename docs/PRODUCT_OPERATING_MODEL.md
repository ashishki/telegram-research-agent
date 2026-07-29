# Product Operating Model

Status: active handoff
Last updated: 2026-07-29

## Current Truth

The product is not dogfood-ready yet.

PRM-18 implemented a deterministic release/dogfood gate and the current gate is
blocked. Dogfood has not started, release readiness is not claimed, and the
runtime has been frozen to prevent old weekly-report automation from producing
new evidence that could be mistaken for PRM dogfood.

Runtime freeze recorded on 2026-07-29:

- `telegram-ai-split-report.timer` stopped and disabled;
- `telegram-bot.service` stopped and disabled;
- `telegram-ai-split-report.service` reset from failed to inactive;
- no Telegram Research Agent systemd service or timer is active;
- no `oc_you` crontab exists;
- no project cron job was found in system cron.

Existing generated artifacts under `data/output/` remain private historical
outputs. They were not deleted, moved, archived, or promoted to dogfood
evidence.

## Single Product Shape

The unified product is:

> Personal Telegram Research Memory + Grounded Assistant.

There should be one operator-facing entrypoint. The operator asks questions,
gets grounded answers with Telegram/archive citations and evidence-class
boundaries, and saves useful memory only through explicit confirmation.

Weekly briefs, Knowledge Library pages, project context views, and MVP Radar
cards are secondary projections over the same memory and evidence graph. They
are not separate products and must not compete for the primary workflow.

## Layers

| Layer | Role | Current state |
| --- | --- | --- |
| Canonical Telegram archive | Private retained source material in SQLite tables such as `raw_posts`, `posts`, and FTS indexes. | Existing. Live ingestion is frozen. |
| Archive search | Bounded SQLite FTS retrieval with metadata and citation identity. | Implemented as local baseline. Vector/hybrid retrieval remains blocked. |
| Curated knowledge | Knowledge Atoms, idea threads, saved notes, watch topics, project links, decisions, experiments. | Partial and fixture-backed; not complete dogfood evidence. |
| Assistant tools | Read-only PRM tools plus confirmation-gated proposal/write tools. | Implemented in slices, but live bot is frozen until safe mode exists. |
| Knowledge Library | Topic-page projection over bounded supplied topic evidence. | Deterministic renderer implemented; not dogfooded. |
| Weekly Brief V3 | Secondary weekly projection over usage, reactions, notes, projects, questions, and failures. | Deterministic fixture projection implemented; no scheduled runtime. |
| MVP Radar | Evidence lens for market/build decisions. | Must be secondary, bounded, and blocked from auto-build/release claims. |
| Legacy reports | V1/V2 Brief, Atlas, Report V2 rollout, old digest/study/MVP commands. | Compatibility-only. Frozen from automatic runtime. |

## MVP Radar Boundary

MVP Radar should not be the product center. It should become one assistant and
brief surface:

- it answers "is there enough evidence to investigate/build?";
- it must separate Telegram evidence from external validation evidence;
- it must not approve a build from Telegram-only demand;
- it must degrade locally when Radar data is missing or failed;
- it must record missing evidence and next validation questions;
- it must not start Frontier, Radar, external research, or report generation
  without an explicit task approval.

In the unified product, MVP Radar is a `decision_evidence_card`, not a weekly
pipeline driver.

## Safe Use Right Now

Use the repository in inspection and deterministic-verification mode only:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
from evals.prm_release_gate import summarize_prm_release_gate, validate_prm_release_gate_receipt

receipt = json.loads(Path("evals/prm18_release_gate_receipt_2026-07-29.json").read_text(encoding="utf-8"))
print(summarize_prm_release_gate(validate_prm_release_gate_receipt(receipt)))
PY
```

Allowed without a separate runtime approval:

- read docs and receipts;
- run deterministic tests and validators;
- inspect process/systemd state;
- inspect artifact names, mtimes, sizes, and manifests when needed without
  committing private generated content;
- develop a safe PRM runtime mode.

Not allowed as dogfood yet:

- live Telegram ingestion;
- reaction sync;
- LLM extraction or LLM judge fan-out;
- Frontier or Radar generation;
- weekly report generation or delivery;
- full archive indexing changes;
- embeddings or vector backend adoption;
- external web research;
- dogfood/release claims.

## Future Operator Entry Point

Before PRM-19 can start, the live entrypoint should be made explicit and safe.

Recommended `prm-assistant` runtime mode:

- one service, disabled by default until dogfood approval;
- no automatic timers;
- `/chat` or ordinary message for grounded questions;
- read-only tools enabled by default;
- proposal tools return drafts only;
- `confirm_save_proposal` is the only durable memory write;
- old generation commands are hidden or disabled:
  `/run_digest`, `/run_mvp_weekly`, old report delivery, ingest, sync, Radar;
- every turn records privacy-safe metadata only: question class, tool names,
  evidence counts, answer usefulness label, latency, cost bucket, and whether
  a save proposal was confirmed.

## Consolidation Plan

1. Keep runtime frozen until a safe PRM mode is implemented.
2. Add a dedicated PRM assistant runtime or bot safe mode that exposes only
   approved read-only and confirmation-gated tools.
3. Replace old weekly-report timers with no timers by default. Later scheduled
   workflows must be PRM-17 registry-backed, idempotent, receipt-producing, and
   explicitly approved.
4. Convert Weekly Brief V3 into a secondary projection generated from real
   PRM usage receipts, not from the old Report V2 rollout gate.
5. Convert MVP Radar into a bounded decision evidence card inside the assistant
   and Weekly Brief V3, with external-evidence separation and no auto-build
   approval.
6. Define PRM-19 dogfood metadata before collecting any dogfood evidence:
   at least 30 real questions, usefulness labels, corrections, saved notes,
   watch topics, decisions, time to useful answer, cost, value, and friction.
7. Run PRM-19 only after human dogfood-start approval and accepted or cleared
   PRM-18 blockers.
8. Run PRM-20 cleanup only after real dogfood evidence justifies what to keep,
   demote, archive, or remove.

## Restarting Legacy Runtime

Do not restart the legacy bot or report timer for PRM dogfood.

If historical compatibility runtime is intentionally needed, record that as a
separate approval and use explicit commands:

```bash
systemctl start telegram-bot.service
systemctl start telegram-ai-split-report.timer
```

Starting either of those reintroduces legacy behavior. The bot includes commands
that can generate artifacts or write local feedback/tag/reminder rows, and the
report timer includes live ingestion and weekly report generation.
