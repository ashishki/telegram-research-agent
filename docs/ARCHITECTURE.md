# Architecture

Status: current
Version: 2.1
Last updated: 2026-08-21

## Product boundary

`telegram-research-agent` is a private Personal Telegram Research Memory and Grounded Assistant for one operator. Search and grounded answers are the primary product. Reports are optional secondary projections.

## Active flow

```text
Telegram / CLI / Eval
        |
        v
PRM application service
        |
        +-- request routing and OperatorContext
        +-- archive and saved-memory retrieval
        +-- project context
        +-- evidence quality and approved claim ledger
        +-- bounded synthesis or deterministic fallback
        +-- final-answer verification
        +-- feedback and confirmation-gated actions
        |
        v
SQLite archive + optional local sidecars + approved provider calls
```

## Layers

### Interfaces

- Telegram polling and callback adapter;
- compact PRM CLI;
- private Eval V2 harness.

Interfaces must call the same PRM application boundary. They must not rebuild routing, retrieval or synthesis independently.

### Application

The application service owns one request lifecycle:

1. normalize input;
2. select one workflow;
3. require project clarification when needed;
4. call the research/chat path;
5. render one answer contract;
6. verify the final answer;
7. return a side-effect-free response object.

### Domain contracts

- `OperatorContext` — ephemeral request identity and workflow;
- evidence item — relevance and evidence quality kept separate;
- approved claim ledger — claims allowed into synthesis;
- project decision — one bounded recommendation or explicit no-action;
- interaction receipt — private metadata, not automatic proof of usefulness.

### Retrieval

Canonical data remains SQLite `raw_posts`, `posts` and `posts_fts`.

Default policy:

- exact and most archive queries: SQLite FTS with deterministic fallback;
- local hash-vector sidecar: fallback only on FTS miss;
- query rewriting: bounded and job-specific;
- API dense sidecar: evaluation adapter only until a meaningful holdout gain exists;
- source links and duplicate/repost identity are preserved.

### Evidence and generation

```text
retrieved evidence
  -> evidence quality
  -> candidate claims
  -> approved claim ledger
  -> synthesis
  -> final rendered-answer verification
```

Current-fact requests fail closed until an approved external verification path runs. Repeated Telegram commentary is not automatically independent evidence.

External watch is not a current runtime capability. Confirmed `watch_topic`
memory is durable intent only; it cannot authorize polling, external fetches,
or notifications. ADR-008 specifies a future source-bounded sidecar subject to
separate operator evidence and approval.

### Local deep research contract

`archive_to_action` uses a bounded five-phase contract:

```text
plan -> gather -> gap-check -> synthesise -> verify
```

`plan` creates phrase-preserving local queries. `gather` pools up to 32 local
archive candidates. `gap-check` identifies missing direct or replayable-practice
evidence and may spend one additional bounded archive search on targeted local
queries. `synthesise` sees at most 12 cited excerpts and selects at most eight
sources. `verify` retains the existing answer and claim gates. No phase sends
the raw corpus, starts a container, runs live web search, or mutates canonical
archive data.

### Durable actions

Conversation is ephemeral by default. Notes, watches, project links, actions and experiments are written only through explicit confirmation. Profile, project configuration, code and external systems are never mutated automatically.

## Runtime boundary

Active runtime templates:

- `systemd/telegram-prm-assistant.service`;
- `systemd/telegram-prm-archive-refresh.service`;
- `systemd/telegram-prm-archive-refresh.timer`.

Report-era timers and services are compatibility history.

## Compatibility boundary

The repository retrofit uses a strangler approach:

- new PRM interfaces call the application boundary;
- the old handler and CLI implementations remain behind compatibility modules;
- old report modules are not imported by the active PRM interface;
- a compatibility module is removed only after callers and focused tests are migrated;
- Git branches/tags preserve executable history; dead Python is not stored under `src/archive`.

## Non-goals

- public SaaS or multi-user permissions;
- a new vector database service;
- a graph database;
- a second bot;
- unrestricted autonomous web research;
- automatic long-term preference learning;
- a new weekly-report product.
