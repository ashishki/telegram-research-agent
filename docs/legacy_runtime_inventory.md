# Legacy Runtime Inventory

Status: active cleanup boundary
Last updated: 2026-08-13

## Active PRM Templates

Only these repo systemd templates are current PRM workflows:

- `systemd/telegram-prm-assistant.service`
- `systemd/telegram-prm-archive-refresh.service`
- `systemd/telegram-prm-archive-refresh.timer`

All report-era templates are preserved in
`systemd/archive/legacy_report_era/`. This archive does not change installed
host units or authorize a systemd operation.

## Code Requiring Migration

The following report-era modules remain in place because active modules or
tests import them. They must not be moved or deleted until a replacement and
focused migration tests exist:

| Module | Current dependency evidence | Required before cleanup |
| --- | --- | --- |
| `src/output/weekly_intelligence_brief.py` | `weekly_intelligence_orchestrator`, split report path, PI facade, and tests | replace callers or retain a compatibility adapter |
| `src/output/knowledge_atlas_report.py` | `weekly_intelligence_orchestrator`, split report path, and tests | replace callers or retain a compatibility adapter |
| `src/assistant/semantic_retrieval.py` | PI facade, main entrypoint, and semantic retrieval tests | migrate or explicitly retain curated search contract |
| `src/output/weekly_run_manifest.py` | PI facade and report/knowledge renderers/tests | extract active manifest contract first |

## Approval Rule

An archive/delete proposal for any code row must state the exact replacement,
current callers, migration risk, focused verification command, and explicit
operator approval. This rule is separate from the completed documentation and
repo-template archive work.
