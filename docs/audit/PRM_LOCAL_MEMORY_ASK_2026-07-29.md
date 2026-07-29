# PRM Local Memory Ask Receipt - 2026-07-29

Status: implemented local preview

## Scope

This change adds a user-facing local command:

```text
PYTHONPATH=src python3 src/main.py memory ask "<question>"
```

Optional scope controls:

```text
--project <name>
--week <YYYY-WNN>
--limit <n>
--json
```

## Product Behavior

`memory ask` is a local evidence brief over existing PRM memory surfaces:

- deterministic route from the operator question;
- bounded SQLite Telegram archive search;
- curated intelligence search;
- project-context decision support when `--project` is provided or the query is
  project/application-oriented;
- external-verification request receipt for fresh, current, or high-stakes
  questions.

It is meant to answer practical operator questions such as:

- "what evidence do I have for this idea?";
- "which posts or knowledge notes support this?";
- "how does this apply to a project?";
- "is this fresh/high-stakes enough that I need external verification?"

## Boundary

The command does not:

- call an LLM;
- send bounded Telegram snippets to a provider;
- run external web research;
- start Telegram services;
- run startup migrations;
- generate reports;
- write memory or feedback rows.

Telegram `prm-assistant` and LLM-backed `/chat` remain separate activation
paths behind explicit dogfood-start/privacy approval.

## Evidence

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_cli.py -q
13 passed, 3 subtests passed in 4.95s
```

```text
PYTHONPATH=src python3 src/main.py memory ask --help
exit=0; help displayed memory ask options; retrieval was not run
```

```text
python3 tools/test_tiers.py focused-prm
102 passed, 6 subtests passed in 14.58s
```

```text
python3 tools/test_tiers.py fast-contract
209 passed, 9 subtests passed in 52.30s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, LLM calls,
systemd starts, startup migrations, or production database writes were
performed.
