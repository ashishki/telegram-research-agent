# ADR-009: Personal Search And Topic News In One Bot

Date: 2026-09-17
Status: registered by owner instruction; launch prompt defines end-to-end local implementation when assigned, runtime adoption not approved.

## Context and authority

The owner requested an evidence-based audit, then implementation cards and deep
review boundaries, and finally instructed: «нужно внести и дать промт для запуска
агента имплементатора с указанием как проводить дип ревью».
This authorizes registering the queue and launch/review documents. It does not
start implementation, a reviewer or production actions. The old RFX-only
restructuring freeze must not redirect a subsequently assigned PRM-SN task.
The owner then clarified: «у промта должен быть гол сделать от и до».
Accordingly, the standard launch prompt now assigns the whole local PRM-SN goal,
not only its first card. Editing that prompt does not execute the goal.

## Decision

Evolve the existing PRM application and external_watch into one personal bot:
archive research, controlled public verification, useful on-demand topic
editions, then confirmed subscriptions. Keep SQLite/FTS, useful sidecars,
confirmation and privacy boundaries. UTD is a specific source/profile scope.
Do not default to a rewrite, new vector database, second bot, SaaS or restoring
the legacy weekly-report pipeline.

Register twelve bounded implementation tasks and five engineering phase reviews
plus a post-pilot review in docs/tasks.md. Detailed acceptance and rollback are
in docs/PRM_SEARCH_NEWS_PLAN.md; tests/measurement rules in
docs/PRM_SEARCH_NEWS_EVAL.md. The standard assignment covers all twelve tasks,
DR-1 through DR-5 and corrections, integrated verification and a pilot packet.
Start with the first unfinished task and continue after passed engineering
gates. Pilot execution and post-pilot review remain separately authorized.

## Review

Apply the existing Playbook mechanism and REVIEW_POLICY. Separate read-only
Codex exec reviewer: gpt-5.6-terra, reasoning high, with observed runtime identity
recorded. Immediate safety triggers still apply inside phases. A task critic is
not a phase gate; reviews cannot grant human completion or runtime authority.

## Boundaries preserved

Explicit task assignment permits its local code, fixtures and review scope.
Public search permission and private-context provider permission remain distinct.
Memory/profile/subscription effects require exact confirmation. Live jobs,
notifications, timers, production migrations, private archive egress, external
embeddings, release/dogfood and compatibility removal require their actual
separate authorization. Existing UTD/RFX statuses and dated approval receipts
are not rewritten or broadened by this ADR. ADR-001 and PRM-19/20 human gates
are not declared complete.

## Consequences and rollback

The task graph, current handoff and active instruction pointers now agree.
General external search/news are planned capabilities, not observed runtime.
Each phase supplies a safe feature-off/fallback rollback; no data deletion is
needed to adopt this direction. If new independent evidence shows retrieval is
the dominant bottleneck, revisit priorities through a scoped decision rather
than silently introducing new infrastructure.
