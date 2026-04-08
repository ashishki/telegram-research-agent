# Memory Inspection — Operator Guide

## Overview

The `memory` CLI subcommand group provides scope-first inspection of the four unified memory
surfaces: signal evidence items, decision journal, project snapshots, and insight suppression.
Use these commands to debug weekly outputs, investigate why an idea was suppressed, or check
whether evidence is being populated correctly.

All commands require `AGENT_DB_PATH` to point to the agent database. Migrations are run
automatically on each invocation.

```
python -m src.main memory <subcommand> [flags]
```

---

## Subcommands

### inspect-evidence

Show `signal_evidence_items` scoped by project, week, or evidence kind.

```
python -m src.main memory inspect-evidence [--project NAME] [--week LABEL] [--kind KIND] [--limit N]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--project` | all projects | Filter by project name (JSON containment match on `project_names_json`) |
| `--week` | all weeks | Filter by exact ISO week label, e.g. `2026-W14` |
| `--kind` | all kinds | Filter by evidence kind: `strong_signal`, `manual_tag`, `project_insight_source`, `study_source`, `decision_support` |
| `--limit` | 20 | Maximum rows to return |

**Output fields per row**

```
[week_label] evidence_kind | source_channel | posted_at
  excerpt: <first 120 chars of excerpt_text>
  url: <message_url or n/a>
  reason: <selection_reason>
```

**Common use cases**

```bash
# See all strong signals for a specific project this week
python -m src.main memory inspect-evidence --project telegram-research-agent --week 2026-W14 --kind strong_signal

# Check that manual tags are being recorded
python -m src.main memory inspect-evidence --kind manual_tag --limit 10
```

---

### inspect-decisions

Show `decision_journal` entries scoped by decision scope, status, or project.

```
python -m src.main memory inspect-decisions [--scope SCOPE] [--status STATUS] [--project NAME] [--limit N]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--scope` | all scopes | Filter by `decision_scope`: `signal`, `insight`, `study`, `project` |
| `--status` | all statuses | Filter by `status`: `acted_on`, `ignored`, `deferred`, `rejected`, `completed` |
| `--project` | all projects | Filter by `project_name` |
| `--limit` | 20 | Maximum rows to return |

**Output fields per row**

```
[recorded_at] scope/status | ref=subject_ref_type:subject_ref_id
  reason: <reason or n/a>
```

**Common use cases**

```bash
# Check recent acted-on signals
python -m src.main memory inspect-decisions --scope signal --status acted_on

# See rejected insights from this week
python -m src.main memory inspect-decisions --scope insight --status rejected --limit 10

# Check study completions
python -m src.main memory inspect-decisions --scope study
```

---

### inspect-snapshots

Show `project_context_snapshots` with week labels and signal counts.

```
python -m src.main memory inspect-snapshots [--stale-only]
```

**Flags**

| Flag | Description |
|---|---|
| `--stale-only` | Show only snapshots older than 2 weeks (not refreshed recently) |

**Output fields per row**

```
project_name | week=snapshot_week_label | signals=linked_signal_count | updated=updated_at
```

**Common use cases**

```bash
# Check which projects have stale snapshots
python -m src.main memory inspect-snapshots --stale-only

# Show all snapshot freshness at a glance
python -m src.main memory inspect-snapshots
```

---

### inspect-suppression

Look up rejection memory and recent decision history for a specific insight title.

```
python -m src.main memory inspect-suppression --title "TITLE"
```

**Required flags**

| Flag | Description |
|---|---|
| `--title` | Insight title to look up. The title is normalized to a fingerprint before lookup. |

**Output**

```
Fingerprint: <normalized fingerprint>
Rejection memory: <row or 'not found'>
Recent decisions (N):
  [recorded_at] status — reason
```

**Common use cases**

```bash
# Debug why an insight keeps getting suppressed
python -m src.main memory inspect-suppression --title "[Implement] telegram-research-agent — Add retry logic"

# Check if an idea was ever acted on
python -m src.main memory inspect-suppression --title "[Build] Lightweight cost tracker"
```

---

## Weekly Troubleshooting Checklist

Use this sequence to debug a weekly run where the output seems wrong.

**1. Evidence not populated**

```bash
python -m src.main memory inspect-evidence --week 2026-W14 --limit 5
```

Expected: rows should appear after `score` and after manual tagging (`record_post_tag`).
If empty: check that `score_posts` ran and that `signal_evidence_items` has rows for the week.

**2. Repeated ideas in recommendations**

```bash
python -m src.main memory inspect-decisions --scope insight --status rejected --limit 10
```

Expected: recent rejected insights appear here. If an idea reappears, check
`inspect-suppression --title "..."` to see whether rejection memory is populated.

**3. Project context snapshots outdated**

```bash
python -m src.main memory inspect-snapshots --stale-only
```

Expected: no rows, or rows for projects not updated recently. If stale snapshots appear,
run the project mapping step to refresh them.

**4. Acted-on signals not contributing to study plan**

```bash
python -m src.main memory inspect-decisions --scope signal --status acted_on --limit 10
```

Expected: recent acted-on signals appear. If empty, check that `record_feedback` is
being called and that the `decision_journal` write is not failing silently.

---

## Decision Scope Reference

| Scope | Written by | Meaning |
|---|---|---|
| `signal` | `record_decision_for_feedback` | User feedback on a post (acted_on, skipped, marked_important) |
| `insight` | `record_decisions_for_triage` | Weekly insight triage outcome (do_now, backlog, reject_or_defer) |
| `study` | `record_study_completion_decision` | Study plan completion for a week |
| `project` | reserved | Future project-level decisions |

---

## Evidence Kind Reference

| Kind | Written by | Meaning |
|---|---|---|
| `strong_signal` | `record_signal_evidence_for_scored_posts` | Auto-scored strong/watch posts |
| `manual_tag` | `record_signal_evidence_for_manual_tag` | Posts explicitly tagged by the user |
| `project_insight_source` | reserved | Evidence linked to a project insight |
| `study_source` | reserved | Evidence used in a study plan |
| `decision_support` | reserved | Evidence supporting a decision |
