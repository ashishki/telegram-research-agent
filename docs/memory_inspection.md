# Memory Inspection — Operator Guide

## Overview

The `memory` CLI subcommand group provides scope-first inspection of unified
memory and audit surfaces: signal evidence items, decision journal, project
snapshots, insight suppression, Research Brief receipts, and Channel
Intelligence derived rows. Use these commands to debug weekly outputs,
investigate why an idea was suppressed, or check whether evidence, receipt audit
metadata, and intelligence refresh rows are being populated correctly.

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
python -m src.main memory inspect-snapshots [--stale-only] [--include-non-curated]
```

**Flags**

| Flag | Description |
|---|---|
| `--stale-only` | Show only snapshots older than 2 weeks (not refreshed recently) |
| `--include-non-curated` | Include active DB projects not listed in `projects.yaml` |

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

### diagnose-project-signals

Show why digest topics did or did not become linked Telegram signals for active projects.

```
python -m src.main memory diagnose-project-signals [--week LABEL] [--limit N] [--json]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--week` | current ISO week | Digest week to inspect, e.g. `2026-W20` |
| `--limit` | 10 | Maximum digest topics to consider |
| `--json` | false | Print the raw diagnostic payload |

Use this when `project_context_snapshots.linked_signal_count` is zero across projects. It separates
keyword vocabulary problems from pipeline problems: no keyword overlap, excluded keywords, matching
posts without links, or already-linked topics. The command follows the curated project registry in
`src/config/projects.yaml`, so stale GitHub-synced rows do not dominate the output.

---

### inspect-receipts

Inspect Research Brief receipt audit metadata by week, receipt ID, digest ID,
artifact path, Telegraph URL, or verification status.

```
python -m src.main memory inspect-receipts [--week LABEL] [--receipt-id ID] [--digest-id ID] [--artifact-path PATH] [--telegraph-url URL] [--status STATUS] [--limit N]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--week` | all weeks | Filter by exact ISO week label |
| `--receipt-id` | all receipts | Filter by stable receipt ID |
| `--digest-id` | all digests | Filter by linked `digests.id` |
| `--artifact-path` | all artifacts | Match Markdown, JSON, or HTML artifact path |
| `--telegraph-url` | all URLs | Filter by delivered Telegraph URL |
| `--status` | all statuses | Filter by `pending`, `verified`, `needs_review`, `failed`, or `waived` |
| `--limit` | 10 | Maximum receipts to return |

**Output fields per receipt**

```
Receipt <receipt_id>
  source_of_truth: research_brief_receipts row id=<id> plus linked digests/signal_evidence_items/llm_usage/artifacts
  refresh_rule: created once after generation; delivery and verification fields update as lifecycle steps complete
  retrieval_path: receipt_id, week_label, digest_id, artifact path, or Telegraph URL
  debug_surface: identity, evidence window, source set, model/config fingerprints, artifacts, delivery refs, verification, health flags
```

**Common use cases**

```bash
# Inspect the receipt for a weekly brief
python -m src.main memory inspect-receipts --week 2026-W22

# Find the audit record behind a delivered Telegraph article
python -m src.main memory inspect-receipts --telegraph-url https://telegra.ph/brief

# List receipts needing deterministic or operator follow-up
python -m src.main memory inspect-receipts --status needs_review
```

---

### inspect-core-receipt

Print the Core-compatible Research Brief receipt JSON. Add
`--verify-evidence` to include deterministic local lookup checks for the
derived Core `evidence_refs`.

```
python -m src.main memory inspect-core-receipt [--week LABEL] [--receipt-id ID] [--digest-id ID] [--artifact-path PATH] [--telegraph-url URL] [--status STATUS] [--limit N] [--verify-evidence]
```

With `--verify-evidence`, the JSON includes `evidence_verification.status`
(`passed`, `failed`, or `needs_review`), resolved `signal_evidence_item` IDs,
checked Telegram source links, failures, and review notes. The check uses only
local SQLite rows and Telegram post URL shape.

---

### inspect-artifact-feedback

Inspect operator feedback that targets a specific artifact section, item, or
evidence group.

```
python -m src.main memory inspect-artifact-feedback [--week LABEL] [--artifact-type TYPE] [--artifact-path PATH] [--digest-id ID] [--feedback VALUE] [--limit N]
```

Feedback values are `useful`, `weak`, `noisy`, or `decision_impacting`.

---

### explain-source-downrank

Explain why a source/channel is being down-ranked from observed local behavior:
noise buckets, missing source links, low-signal tags, skipped feedback, source
observations, and low project relevance.

```
python -m src.main memory explain-source-downrank [--channel USERNAME] [--days N] [--limit N]
```

The output is deterministic and does not store model-generated source trust as
fact.

---

### review-receipt

Record an operator review status for a Research Brief receipt. This updates
verification fields only; it does not change reader-facing reports.

```
python -m src.main memory review-receipt (--receipt-id ID | --week LABEL | --digest-id ID) --status STATUS [--notes TEXT] [--checked-by NAME]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--receipt-id` | optional | Review a specific receipt ID |
| `--week` | optional | Review the latest receipt for a week |
| `--digest-id` | optional | Review the receipt linked to a digest row |
| `--status` | required | One of `verified`, `waived`, `needs_review`, or `failed` |
| `--notes` | none | Operator note explaining the review decision |
| `--checked-by` | `operator` | Local actor label to store in `checked_by` |

**Common use cases**

```bash
# Accept a receipt after manual review
python -m src.main memory review-receipt --receipt-id rbr_... --status verified --notes "Source links checked"

# Waive a known issue for the week
python -m src.main memory review-receipt --week 2026-W22 --status waived --notes "Telegraph outage; HTML fallback delivered"
```

---

### inspect-channel-intelligence

Inspect derived Channel Intelligence rows: repeated claims, narratives, source
observations, entity links, and project links.

```
python -m src.main memory inspect-channel-intelligence [--kind KIND] [--week LABEL] [--project NAME] [--topic LABEL] [--channel NAME] [--status STATUS] [--limit N]
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--kind` | `all` | One of `all`, `claims`, `narratives`, `sources`, `entity-links`, `project-links` |
| `--week` | all weeks | Filter by ISO week label |
| `--project` | all projects | Filter by active project scope |
| `--topic` | all topics | Filter by topic label |
| `--channel` | all channels | Filter claims by occurrence source and source observations by channel |
| `--status` | all statuses | Filter claim or narrative status |
| `--limit` | 10 | Maximum rows per section |

The command prints source-of-truth, refresh-rule, retrieval-path, and
debug-surface metadata before scoped row details. Row details include claim and
narrative evidence IDs, source observation counters, entity link provenance,
project link match reasons, `refresh_scope_json`, and `counters_json`.

**Common use cases**

```bash
# Inspect all Channel Intelligence rows for a project/week
python -m src.main memory inspect-channel-intelligence --week 2026-W22 --project telegram-research-agent

# Inspect source counters for a specific channel
python -m src.main memory inspect-channel-intelligence --kind sources --channel source_a

# Inspect rejected narrative candidates
python -m src.main memory inspect-channel-intelligence --kind narratives --status rejected
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

If snapshots are fresh but all `signals=0`, run:

```bash
python -m src.main memory diagnose-project-signals --week 2026-W14
```

Expected: each project shows whether digest topics were dropped by vocabulary mismatch or remained
`candidate_unlinked` because matching posts were found but `post_project_links` was not populated.

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
