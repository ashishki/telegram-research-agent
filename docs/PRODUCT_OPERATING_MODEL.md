# Product Operating Model

Status: active handoff
Last updated: 2026-08-11

## Current Truth

The product is not dogfood-started yet.

PRM-18 implemented a deterministic release/dogfood gate. After PRM-24, PRM-26,
and PRM-28, the current post-PRM28 receipt records deterministic local product
RAG readiness for the accepted no-vector path, but the dogfood gate is still
blocked because explicit PRM-19 dogfood-start approval is not recorded. Dogfood
has not started, release readiness is not claimed, and the runtime remains
frozen to prevent old weekly-report automation from producing new evidence that
could be mistaken for PRM dogfood.

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

A dedicated safe runtime now exists in code as `src/main.py prm-assistant` and
as a repo unit template at `systemd/telegram-prm-assistant.service`. It has not
been installed, enabled, started, or treated as dogfood.

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
| Assistant tools | Read-only PRM tools plus confirmation-gated proposal/write tools. | Safe `prm-assistant` entrypoint implemented; disabled/not started until dogfood approval. |
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

For the current post-PRM28 gate, inspect:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
from evals.prm_release_gate import summarize_prm_release_gate, validate_prm_release_gate_receipt

receipt = json.loads(Path("evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json").read_text(encoding="utf-8"))
print(summarize_prm_release_gate(validate_prm_release_gate_receipt(receipt)))
PY
```

Allowed without a separate runtime approval:

- read docs and receipts;
- run deterministic tests and validators;
- ask local PRM memory with `PYTHONPATH=src python3 src/main.py memory ask
  "<question>"`; this is local-only and does not call LLMs, external search,
  Telegram services, startup migrations, generation jobs, or write tools;
- inspect process/systemd state;
- inspect artifact names, mtimes, sizes, and manifests when needed without
  committing private generated content;
- inspect the safe PRM runtime command and unit template without starting it.

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

## Safe Operator Entry Point

The explicit safe entrypoint is:

```bash
PYTHONPATH=src python3 src/main.py prm-assistant
```

Do not run this as dogfood until the human operator explicitly approves
dogfood start.

For immediate local use, prefer:

```bash
PYTHONPATH=src python3 src/main.py memory ask "какие есть подтверждения по моей идее?"
```

This returns a local evidence brief. It does not perform LLM synthesis over
archive snippets.

Completed pre-PRM-19 UX block:

- PRM-18A implemented the operator-facing LLM chat contract and explicit
  provider-egress switch as a docs-only contract; it does not approve provider
  calls, service starts, dogfood, or production DB writes.
- PRM-18B implemented a CLI chat harness over the existing PI chat/RAG path
  with fake-provider tests by default.
- PRM-18C aligned Telegram `prm-assistant` UX and the start/stop runbook
  without installing, enabling, or starting the service.
- The deep review boundary for this block is recorded at
  `docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.

PRM-18A contracted command surfaces:

- current local-only evidence: `PYTHONPATH=src python3 src/main.py memory ask "<question>"`;
- current local-only receipt: `PYTHONPATH=src python3 src/main.py memory ask --json "<question>"`;
- PRM-18B one-shot command:
  `PYTHONPATH=src python3 src/main.py memory ask --llm-approved --allow-provider-egress "<question>"`;
- PRM-18B interactive command:
  `PYTHONPATH=src python3 src/main.py memory chat --allow-provider-egress`;
- Telegram local research command after approved runtime start:
  `/research <question>` or ordinary text inside the disabled `prm-assistant`
  runtime;
- Telegram editor brief command after approved runtime start:
  `/brief <question>` for local-only source-backed theses;
- PRM-18C Telegram LLM parity command after separate provider-egress approval:
  `/chat <question>` with `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`.

Any LLM-backed surface must print sources, archive-support status, unknowns or
external-verification needs, write status, and an explicit privacy/cost line.
Without the explicit provider-egress switch, the product must stay local-only or
refuse before sending bounded Telegram snippets to a provider.

Future polished assistant target:

- specified in `docs/personal_research_memory_product_contract.md` and
  scheduled in `docs/tasks.md`;
- PRM-21 records the contract; PRM-22 implements a fixture-first linked-source
  resolver/cache layer, and PRM-23 implements a bounded fixture-first
  `memory research` planner/CLI;
- expected to add archive search plus approved linked-source research,
  project-context routing, approach comparison, LLM synthesis, and
  deeper-reading paths;
- not PRM-19 evidence until implemented and explicitly dogfooded;
- not an approval to start live web research, provider egress, services,
  dogfood, production DB writes, durable production cache writes, or
  vector/backend adoption.

Implemented `prm-assistant` runtime mode:

- one service, disabled by default until dogfood approval;
- no automatic timers;
- `/research` or ordinary message for local-only grounded questions;
- `/brief` for local-only source-backed editor/social-post theses;
- short follow-ups can use the last in-process research question for that
  chat; this dialog context is volatile and is not written to the database;
- `/chat` remains the separate LLM-backed command and requires separate
  provider-egress approval plus `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1` before
  use with private snippets;
- read-only tools enabled by default;
- proposal tools return drafts only;
- `confirm_save_proposal` is the only durable memory write;
- ordinary text and voice transcript dispatch to `/research`, not the legacy
  `/message` or `/voice` feedback/reminder router;
- legacy callbacks are disabled, so inline buttons cannot write old decision,
  reminder, or artifact-feedback rows;
- old generation/write commands are blocked:
  `/run_digest`, `/run_mvp_weekly`, old report delivery, ingest, sync, Radar,
  `/feedback_confirm`, direct tags, marks, and reminders.
- startup does not run automatic DB migrations; any production schema migration
  remains a separate approved maintenance action.

## Consolidation Plan

1. Keep legacy runtime frozen.
2. Keep the dedicated PRM assistant runtime disabled until approved dogfood
   start.
3. Replace old weekly-report timers with no timers by default. Later scheduled
   workflows must be PRM-17 registry-backed, idempotent, receipt-producing, and
   explicitly approved.
4. Convert Weekly Brief V3 into a secondary projection generated from real
   PRM usage receipts, not from the old Report V2 rollout gate.
5. Convert MVP Radar into a bounded decision evidence card inside the assistant
   and Weekly Brief V3, with external-evidence separation and no auto-build
   approval.
6. Keep PRM-18A through PRM-18C as the pre-dogfood chat workflow and privacy
   contract baseline.
7. Define PRM-19 dogfood metadata before collecting any dogfood evidence:
   at least 30 real questions, usefulness labels, corrections, saved notes,
   watch topics, decisions, time to useful answer, cost, value, and friction.
8. Run PRM-19 only after human dogfood-start approval. The current post-PRM28
   PRM-18 receipt has deterministic local stop-ship blockers cleared, but the
   explicit dogfood-start approval blocker remains.
9. Run PRM-20 cleanup only after real dogfood evidence justifies what to keep,
   demote, archive, or remove.

## Runtime Commands

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

The safe assistant unit template is `systemd/telegram-prm-assistant.service`.
Installing or starting it is a dogfood-start action and requires the same
explicit approval as PRM-19.

Future approved activation runbook:

```bash
systemd-analyze verify systemd/telegram-prm-assistant.service
sudo install -m 0644 systemd/telegram-prm-assistant.service /etc/systemd/system/telegram-prm-assistant.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-prm-assistant.service
systemctl status telegram-prm-assistant.service --no-pager
journalctl -u telegram-prm-assistant.service -n 100 --no-pager
```

Rollback to disabled:

```bash
sudo systemctl stop telegram-prm-assistant.service
sudo systemctl disable telegram-prm-assistant.service
sudo rm -f /etc/systemd/system/telegram-prm-assistant.service
sudo systemctl daemon-reload
```

Do not run the activation commands until PRM-19 dogfood-start approval is
explicitly recorded.
