# RFX Repository Retrofit

Status: active
Date: 2026-08-16
Baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`

## Goal

Make the repository represent one current product: Personal Telegram Research Memory and Grounded Assistant. Reduce agent context, import coupling and maintenance cost without changing retrieval semantics or deleting recoverable history.

## Strategy

Use a strangler retrofit:

1. preserve the baseline in an archive branch;
2. consolidate active documentation;
3. introduce one PRM application service;
4. route active Telegram, CLI and eval interfaces through that service;
5. move the old monolithic handler implementation behind a lazy compatibility facade;
6. separate active tests from report-era compatibility tests;
7. remove tracked generated artifacts;
8. migrate active callers away from report-era code;
9. collect 15-20 labelled operator interactions;
10. delete only code and tests with no active callers or observed use.

## Active versus historical

Active:

- Telegram PRM assistant;
- archive ingestion and search;
- evidence quality and claim verification;
- project decision and current-fact boundaries;
- confirmation-gated saved knowledge/actions;
- Eval V2 and focused safety checks.

Compatibility:

- digest and report commands;
- Weekly Brief, Atlas, Radar and Frontier;
- old CLI entrypoint;
- historical PI/report facade methods;
- old eval adapters and public receipts.

## Archive policy

- Markdown, ADRs, audits and task history may live under `docs/archive/`.
- Executable dead code is deleted from the active branch after caller migration.
- `src/archive` and `tests/archive` are forbidden.
- Database migrations, rollback logic, privacy, SSRF, confirmation, current-fact and corruption tests are never removed merely for size.
- The archive branch and Git history are the executable-code archive.

## Commit policy

Separate:

1. documentation and pure moves;
2. application-boundary creation;
3. import/dispatch rewrites;
4. behavior-preserving caller migration;
5. generated-artifact deletion;
6. dead-code deletion;
7. final review fixes.

No force push. No giant mixed refactor commit.

## Stop conditions

Stop destructive cleanup when:

- an active caller remains;
- focused tests do not cover the replacement;
- a migration or privacy boundary changes;
- a module is required by installed runtime configuration;
- operator smoke evidence is needed to decide whether a product surface is useful;
- CI or the deep review finds a P0/P1 regression.

## Completion criteria

- one active application entrypoint;
- one active architecture and task queue;
- active bot imports no report-era modules;
- focused PRM tier excludes report-era tests;
- tracked generated outputs are gone;
- legacy commands are explicit, not default;
- current runtime answers are contract-equivalent before and after the structural changes;
- residual compatibility debt is recorded with callers and removal gates.
