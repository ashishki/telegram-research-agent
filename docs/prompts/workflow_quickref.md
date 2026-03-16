# Workflow Quick Reference

---

## Entry Point

There is one way to start the development cycle:

```
Send docs/prompts/workflow_orchestrator.md to Claude Code (Strategist instance).
No variables. No setup. Just paste and send.
```

The orchestrator reads `docs/tasks.md` to determine the current phase,
drives Implement → Review → Fix automatically, updates `docs/tasks.md` after each phase,
and loops until all phases are complete or a blocker is found.

---

## What the Orchestrator Does

```
Read tasks.md
  │
  └─▶ Find current phase (lowest phase with [ ] tasks)
        │
        ├─▶ Spawn Codex Implementer (general-purpose agent)
        │     └─▶ Implements all tasks in phase
        │
        ├─▶ Update tasks.md: [ ] → [~]
        │
        ├─▶ Spawn Claude Reviewer (Explore agent)
        │     ├─▶ PASS → continue
        │     └─▶ ISSUES FOUND:
        │               ├─▶ Spawn Codex Fixer (general-purpose agent)
        │               └─▶ Spawn Reviewer again (targeted re-check)
        │                     ├─▶ PASS → continue
        │                     └─▶ SAME ISSUES AGAIN → mark [!], stop, report to user
        │
        ├─▶ Update tasks.md: [~] → [x]
        │
        └─▶ Loop to next phase
```

---

## When the Loop Stops

| Condition | tasks.md state | Action needed |
|---|---|---|
| All phases `[x]` | All done | MVP complete — proceed to ops setup |
| Task marked `[!]` | Blocked | User must resolve blocker manually, then re-run orchestrator |
| Agent unrecoverable error | `[!]` set on failed task | Check journal/logs, fix manually, re-run |

---

## Resuming After a Stop

The orchestrator is stateless — it reads all state from `docs/tasks.md` on every run.

To resume:
1. Resolve the blocker (fix `[!]` task manually or clear the `[!]` mark)
2. Re-send `workflow_orchestrator.md` to Claude Code
3. It picks up from the current state automatically

---

## Manual Overrides

If you need to re-run a specific phase without re-running previous phases:
1. Open `docs/tasks.md`
2. Change the phase tasks back to `[ ]`
3. Re-send the orchestrator prompt

To skip a phase (not recommended):
1. Manually mark all its tasks `[x]` in `docs/tasks.md`
2. The orchestrator will skip it

---

## Phase Reference

| Phase | Name | Key files Codex creates |
|---|---|---|
| 1 | Project Scaffold | schema.sql, migrate.py, client.py, main.py, settings.py, channels.yaml, .gitignore |
| 2 | Bootstrap Ingestion | telegram_client.py, bootstrap_ingest.py, run_bootstrap.sh |
| 3 | Normalization | normalize_posts.py |
| 4 | Topic Detection | cluster.py, detect_topics.py |
| 5 | Weekly Pipeline | incremental_ingest.py, telegram-ingest.service/timer, run_weekly.sh |
| 6 | Digest Generation | generate_digest.py, telegram-digest.service/timer |
| 7 | Recommendations | generate_recommendations.py |
| 8 | Project Mapping | map_project_insights.py |
| 9 | Hardening | healthcheck.sh + retry/logging across all modules |

---

## Individual Agent Prompts (manual use only)

These exist for ad-hoc use or debugging — the orchestrator uses them as embedded templates:

| File | Use when |
|---|---|
| `workflow_codex_implementer.md` | Manually re-running a single phase implementation |
| `workflow_claude_reviewer.md` | Manually reviewing a specific phase |
| `workflow_codex_fixer.md` | Manually applying fixes from a review |

---

## tasks.md Status Legend

| Symbol | Meaning |
|---|---|
| `[ ]` | Not started |
| `[~]` | Implemented, pending review |
| `[x]` | Complete (implemented + reviewed) |
| `[!]` | Blocked — needs human input |
