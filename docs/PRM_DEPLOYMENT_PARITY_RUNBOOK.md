# PRM Deployment Parity Runbook

Status: active read-only verification procedure
Updated: 2026-08-16

## Goal

Determine which commit, entrypoint, systemd unit, working directory, and runtime flags are actually producing Telegram answers before attributing behavior to repository code.

This runbook performs no deploy, restart, migration, database write, Telegram send, or provider call.

## Expected repository state

Candidate and target branch: `master`. Record a specific candidate SHA in the
private receipt; a historical feature branch is not a deployment target.

The active repository template expects a PRM assistant entrypoint equivalent to:

```text
python -m prm.cli assistant
```

Do not assume the installed unit matches the repository template.

## 1. Identify the checkout and Git state

On the VPS:

```bash
cd /srv/openclaw-you/workspace/telegram-research-agent

git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short --branch
git log -1 --format='%H %cI %s'
```

Compare local and remote refs without changing local refs:

```bash
git ls-remote origin refs/heads/master
```

Record:

- current branch;
- local HEAD;
- remote candidate HEAD;
- whether the worktree is clean;
- commit timestamp and subject.

## 2. Discover the active unit

```bash
systemctl list-units --type=service --all \
  | grep -Ei 'telegram|prm|research'
```

For the expected unit:

```bash
systemctl status telegram-prm-assistant.service --no-pager
systemctl cat telegram-prm-assistant.service
```

Record:

- unit name;
- fragment path;
- drop-ins;
- enabled/active state;
- reported command.

## 3. Read effective systemd properties

```bash
systemctl show telegram-prm-assistant.service \
  -p FragmentPath \
  -p DropInPaths \
  -p ExecStart \
  -p WorkingDirectory \
  -p EnvironmentFiles \
  -p ActiveEnterTimestamp \
  -p ExecMainStartTimestamp \
  -p MainPID
```

Required checks:

- `ExecStart` uses the intended Python and PRM entrypoint;
- `WorkingDirectory` points to the checkout being inspected;
- the environment file is the intended operator-owned file;
- process start time is later than the deployed checkout update.

## 4. Inspect the actual process

```bash
pid="$(systemctl show -p MainPID --value telegram-prm-assistant.service)"

ps -p "$pid" -o pid,lstart,cmd
readlink -f "/proc/$pid/exe"
readlink -f "/proc/$pid/cwd"
```

A repository pull does not update already imported Python code in a long-running process. If the process start time predates the deployed commit, a restart would be required to activate it, but this runbook does not perform that restart.

## 5. Inspect relevant runtime flags safely

```bash
tr '\0' '\n' <"/proc/$pid/environ" \
  | grep -E '^(PRM_|TELEGRAM_|PYTHONPATH|AGENT_DB_PATH|DATABASE_)' \
  | sed -E 's/((TOKEN|KEY|SECRET|PASSWORD)[^=]*)=.*/\1=[REDACTED]/'
```

Record at minimum:

```text
PRM_TELEGRAM_RAG_LLM_SYNTHESIS
PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS
PRM_ARCHIVE_HYBRID_RETRIEVAL
PRM_ARCHIVE_VECTOR_INDEX_PATH
PRM_TELEGRAM_AUTO_LLM_ROUTER
AGENT_DB_PATH
```

Interpretation:

- synthesis disabled: deterministic renderer is authoritative;
- synthesis enabled without provider egress: no provider synthesis should run;
- hybrid disabled: raw archive retrieval is SQLite FTS-first;
- hybrid enabled without a valid sidecar path: vector fallback may be unavailable;
- provider egress enabled: bounded source snippets may leave the host under the approved product policy;
- a different DB path means local replay must use that exact database in read-only mode.

Do not print secret values into tickets, PR comments, or public artifacts.

## 6. Inspect recent runtime events

```bash
journalctl \
  -u telegram-prm-assistant.service \
  --since '2026-08-16 00:00:00' \
  --no-pager \
  | tail -n 250
```

Look for:

- process restart time;
- import or startup failures;
- route/handler failures;
- provider errors;
- Telegram send failures;
- database path errors.

Do not copy private user questions or archive text into public reports.

## 7. Record the parity receipt

Store an operator-local receipt outside Git tracking with this shape:

```json
{
  "schema_version": "prm_deployment_parity_receipt.v1",
  "checked_at": "<UTC timestamp>",
  "repository_path": "/srv/openclaw-you/workspace/telegram-research-agent",
  "local_head": "<sha>",
  "remote_master": "<sha>",
  "remote_candidate": "<sha>",
  "unit_name": "telegram-prm-assistant.service",
  "fragment_path": "<path>",
  "exec_start_redacted": "<command without secrets>",
  "working_directory": "<path>",
  "process_started_at": "<timestamp>",
  "runtime_flags": {
    "rag_llm_synthesis": false,
    "provider_egress": false,
    "hybrid_retrieval": false,
    "vector_index_configured": false
  },
  "parity": "match|mismatch|unknown",
  "restart_required_for_candidate": true,
  "privacy": {
    "contains_secrets": false,
    "contains_queries": false,
    "contains_archive_text": false,
    "public_artifact": false
  }
}
```

## 8. Decision table

| Observation | Conclusion |
|---|---|
| Active process HEAD equals candidate and process started after deployment | Candidate code may be active |
| Checkout HEAD equals candidate but process started before deployment | Candidate is not active in the process |
| `ExecStart` does not use `prm.cli assistant` | Different runtime path is active |
| Working directory differs from inspected checkout | Repository inspection does not establish runtime parity |
| Candidate branch is not present on VPS | Candidate is not deployed |
| Environment flags differ from replay settings | Replay is not production-equivalent |
| Unit is inactive | Telegram answer came from another service/process or an earlier observation |

## 9. Candidate activation procedure

Activation is outside this read-only runbook and requires explicit operator approval. The controlled sequence is:

1. record current commit and unit receipt;
2. ensure focused checks and owner smoke passed;
3. update only the intended checkout/ref;
4. verify no production DB migration is required;
5. restart only `telegram-prm-assistant.service`;
6. record new process start time and HEAD;
7. run a bounded manual Telegram smoke;
8. preserve the previous commit for rollback.

Do not restart legacy bot/report timers. Do not call the activation PRM-19 dogfood unless the separate dogfood-start approval exists.

## 10. Rollback procedure

If the candidate regresses manual testing:

1. checkout/deploy the recorded previous commit;
2. restart only the active PRM assistant unit;
3. verify process HEAD and start time;
4. rerun the reference query and two negative controls;
5. do not modify or roll back the canonical Telegram database;
6. retain private diagnostic receipts for engineering review.
