# PRM Manual Telegram Assistant Activation - 2026-08-11

Status: active manual test
Recorded at: 2026-08-11 18:27-18:36 CEST

## Scope

The operator approved enabling the local vector/RAG/LLM/Telegram stack for
manual user testing before PRM-19 dogfood. This receipt records that activation.

This is not PRM-19 dogfood evidence, not a release-readiness claim, and not
approval for legacy Telegram services, live web research, external embeddings,
hosted vector services, production database migrations, canonical DB writes, or
compatibility cleanup.

## Activated Runtime State

| Check | Result |
| --- | --- |
| systemd unit | `telegram-prm-assistant.service` |
| unit template | `systemd/telegram-prm-assistant.service` |
| installed state | installed under `/etc/systemd/system/telegram-prm-assistant.service` |
| enabled state | enabled |
| active state | active |
| runtime mode | `prm_assistant` |
| automatic startup migrations | skipped |
| legacy bot/timer | not restarted |
| PRM-19 dogfood | not started |

Unit validation:

```text
systemd-analyze verify systemd/telegram-prm-assistant.service
pass, with unrelated snapd RestartMode warning from the host system unit
```

Status checks:

```text
systemctl is-active telegram-prm-assistant.service
active

systemctl is-enabled telegram-prm-assistant.service
enabled
```

Startup log facts:

- startup used `runtime_mode=prm_assistant`;
- startup explicitly logged that automatic migrations were skipped;
- Telegram bot polling started.

Owner chat identifiers, bot tokens, model keys, and raw Telegram source text are
intentionally omitted from this public receipt.

## Local Vector/RAG State

| Check | Result |
| --- | --- |
| sidecar path | `data/vector/archive_vector.sqlite` |
| git tracking | ignored by `.gitignore`; not committed |
| sidecar size | 62,435,328 bytes |
| sidecar owner/mode | `root:root 644` |
| service read access | `oc_you` can read the sidecar |
| embedding backend | deterministic local hashing |
| external embedding provider egress | false |
| hosted vector service | false |
| canonical DB mutation | false |

Vector-index build summary:

```text
schema_version=archive_vector_index.v1
embedding_model=local_hashing_text_vector.v1
source_rows_scanned=3215
inserted=3313
updated=0
deleted=0
provider_egress=false
canonical_db_mutated=false
```

Hybrid eval summary over the 50-row generated seed gold set:

```text
retrieval_mode=hybrid-local-vector
hit@10=1.0
mrr=1.0
citation_precision=1.0
duplicate_top10_rate=0.004
latency_ms_p95=59.077
reacted_post_searchability=0.967742
no_answer_accuracy=0.0
```

The no-answer gap is handled by the PRM-28 answer gate rather than the raw
retrieval eval. The product answer-gate report remains the source of truth for
no-answer/current-fact refusal behavior.

## Runtime Flags

The host `.env` was updated with non-secret PRM flags:

```text
PRM_ARCHIVE_HYBRID_RETRIEVAL=approved
PRM_ARCHIVE_VECTOR_INDEX_PATH=/srv/openclaw-you/workspace/telegram-research-agent/data/vector/archive_vector.sqlite
PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1
PRM_TELEGRAM_AUTO_LLM_ROUTER=1
PRM_TELEGRAM_RAG_LLM_SYNTHESIS=1
```

Secret values such as Telegram tokens, chat IDs, and LLM API keys are not
recorded here.

## Delivery Check

A short Telegram service-check message was sent through the configured bot API
to confirm delivery to the operator. The delivery check did not include private
source text and did not call an LLM provider.

## Safety Boundary

Performed:

- local vector sidecar build;
- local hybrid retrieval eval;
- systemd unit install/enable/start for `telegram-prm-assistant.service`;
- Telegram delivery check through the configured bot.

Not performed:

- live Telegram ingestion;
- reaction sync;
- legacy `telegram-bot.service` restart;
- legacy report timer restart;
- live web research;
- external embedding call;
- hosted vector service use;
- production database migration;
- canonical DB write;
- private Telegram source packet commit;
- PRM-19 dogfood start;
- release claim.

During manual Telegram tests, `/chat` or LLM auto-routing may send bounded cited
context snippets to the configured provider because
`PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1` and `PRM_TELEGRAM_AUTO_LLM_ROUTER=1` are
enabled. `/research`, `/brief`, and auto-routed research/brief additionally may
send selected bounded RAG snippets/context for Telegram answer synthesis because
`PRM_TELEGRAM_RAG_LLM_SYNTHESIS=1` is enabled.

## Manual-Test UX Repair - 2026-08-11

The first operator manual question produced a low-value answer. The observed
service logs showed the ordinary-message path reached LLM execution, but the
runtime did not expose enough route/retrieval detail. The repair:

- logs the selected PRM auto route without logging message text;
- prevents archive/source questions from being routed to generic chat;
- narrows the editor-brief heuristic so "what was in my posts" stays research
  instead of brief;
- makes Telegram research/brief run local hybrid RAG first, then optionally
  synthesize the bounded RAG context with the configured LLM;
- suppresses LLM usage DB recording for this Telegram synthesis to avoid
  production database writes;
- preserves local RAG fallback if the provider call fails.

Focused validation:

```text
PYTHONPATH=src python3 -m pytest tests/test_handlers.py -q
44 passed
```
