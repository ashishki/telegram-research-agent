# Telegram Personal AI Assistant

Private, single-operator assistant. The current implementation is an archive-
centered alpha; the full target is natural Chat, real AI Search, beautiful
weekly/topic Briefs, controlled Watch and confirmed Act in one conversation.
**The PA specification is a target, not a claim these features already work.**

## Start here

- [Full specification in Russian](docs/PERSONAL_ASSISTANT_SPEC.md): all user
  wishes, UX, weekly reports, search, connectors, Academic Inbox, permissions,
  architecture, models, evidence, operations and full completion criteria.
- [Current handoff](docs/CODEX_PROMPT.md) and
  [Sol implementation assignment](docs/prompts/pa_sol_implementation.md).
- [Compact programme design](docs/design/PA.md),
  [slice registry](docs/design/PA.design.json), [active tasks](docs/tasks.md).
- [Pinned Playbook setup](docs/PLAYBOOK_ADOPTION.md) and
  [review policy](docs/REVIEW_POLICY.md).

## Current implementation versus target

Observed source baseline: `8faee4232cb30e6b6f39cfbd974c151846f79da6`;
reconciliation: 2026-10-06. Deployed state has not been observed.

| Capability | Default/application wiring | Local contract | Live evidence |
| --- | --- | --- | --- |
| Archive Search | Application retrieval/evidence and bounded synthesis seam | PA-04/06 | Not established for current SHA |
| AI Chat | Calls an injected model only with typed per-turn authorization; none by default | PA-03 | Not established |
| Public web/GitHub | Explicit adapter injection; no default web provider | PA-05/06 | Not established |
| Brief/read/export | Versioned brief application methods and private export helpers | PA-07/08 | Owner visual/runtime acceptance pending |
| Watch | Explicit-path SQLite subscriptions/jobs; no general scheduler composition | PA-09 | Historical bounded UTD evidence is separate |
| Mail/calendar/academic, Act, memory/media/ops | Separate local contracts; end-to-end composition remains PAI work | PA-10..17 | Not established |

The historical PA-00 confirmation-context UX regression passes in the current
focused check. Another conversation fixture depended on the calendar date;
its diagnosis and deterministic correction are in
[PAI-00 evidence](docs/verification/PAI-00-reconciliation.md). This is focused
evidence, not a claim that all CI is green. The remaining implementation queue
is [PAI tasks](docs/PA_IMPLEMENTATION_TASKS.md); actual wiring, review and gates
are tracked in [PAI progress](docs/verification/PAI-progress.md).

## Local PA slices and evaluation tooling

All PA slices **PA-00..PA-17** now have local, fail-closed contracts with
deterministic synthetic tests (no live network, account, database, timer or
deployment), and each is registered in the `focused-prm` tier:

- PA-10 `src/prm/mail_connector.py`, PA-11 `src/prm/schedule_connectors.py`
  (calendar + contacts), PA-12 `src/prm/academic_inbox.py`,
  PA-13 `src/prm/confirmed_actions.py`, PA-14 `src/prm/memory_library.py`,
  PA-15 `src/prm/media_connectors.py`, PA-16 `src/prm/model_cost.py`,
  PA-17 `src/prm/operations.py`.
- Every new transport is purpose-separated in `src/prm/capabilities.py` and
  re-checks a typed PA-02 reservation before egress or a write.

Evaluation runs without Codex, through the operator-owned OpenCode Go endpoint:

- `tools/prm_product_ux_eval.py --provider opencode-go` (text/product UX),
- `tools/assistant_answer_judge.py` (archive answers + weekly brief text),
- `tools/assistant_visual_judge.py` (rendered PDF pages / Telegram dialogue,
  vision model `deepseek-v4-flash-vision-exp`),
- `tools/pdf_ocr_crosscheck.py` (optional SotaOCR cross-check),
- `tools/profile_ranked_brief.py` (profile-ranked brief + persona editorial),
- `tools/mimo_code_review.py` (independent read-only deep review via
  `mimo-v2.6-pro`).

These tools are advisory and fail-closed; they are not runtime acceptance.
**PA-18 (full acceptance)** still requires exact-HEAD checks, owner visual
review and authorized real use, and the runtime gates for each connector remain
open.

Original implementation documentation and evidence remain available:
[architecture](docs/ARCHITECTURE.md), [contract](docs/IMPLEMENTATION_CONTRACT.md),
[Academic Inbox handoff](docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md),
[previous README](README.before-pa-20260918.md),
[prior tasks](docs/tasks.before-pa-20260918.md).

## Development setup

```bash
git submodule update --init --checkout -- .playbook/upstream
python -m pip install -r requirements-playbook.txt
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
```

Application tests additionally need `requirements.txt`. New tooling is pinned
to owner Playbook commit `d570163ab17ec3b4245187c778f1e8d89af9690f`, not latest.
It is development-only, not a runtime dependency. See the adoption guide for
Linux/WSL symlink requirements, focused checks and exact design approval.

No private data or secrets in Git. No account, paid model call, service, timer,
production migration or release is enabled by the planning/tooling update.
