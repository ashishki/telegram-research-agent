# PRM-MAT — Mature Integrated Operator Product Roadmap

Status: proposed. This is a documentation-only queue; implementation begins through approved bounded tasks.

## Dependency graph

```text
MAT-0 -> MAT-1 -> MAT-2 -> MAT-3 -> MAT-4 -> MAT-5
MAT-5 -> MAT-6 -> MAT-7 -> MAT-11
MAT-0 -> MAT-8 -> MAT-9
MAT-4 -> MAT-10 -> MAT-12
MAT-7/MAT-9/MAT-11/MAT-12 -> MAT-13 -> MAT-14 -> MAT-15 -> MAT-16
MAT-5/MAT-6/MAT-7/MAT-8/MAT-9/MAT-10/MAT-11/MAT-12/MAT-14/MAT-15/MAT-16 -> MAT-17
MAT-17 -> MAT-18 -> MAT-19 -> MAT-20
```

Phase A: audit, canonical context/workflow, lenses, approved portfolio migration, answer DTO/synthesis, Telegram UX. Phase B: durable interaction and knowledge. Phase C: independent freshness/reactions. Phase D: approved verification and workflow integration. Phase E: recap, evaluation, operations and docs. Phase F: approved smoke, four-week evidence, simplification and portfolio packaging. MAT-8 can start after audit because it is isolated, but schedule remains approval-gated. MAT-10 cannot live-fetch until approval.

## Milestones

First end-to-end usable milestone is PRM-MAT-5: one Telegram request has one context, one workflow, soft lens, approved project choice, validated answer DTO and Russian reader output. It is not validation. Mature private product completion is PRM-MAT-19 only after PRM-MAT-18 real evidence, accepted ops/privacy gates and explicit operator decision. PRM-MAT-20 packages only public-approved evidence.

## Anti-complexity and gates

No new agent framework, vector backend, dashboard, graph database, multi-user model, second bot, public service or report engine. Normal tasks are one integration outcome, <=8 production files/~1000 lines, 1–3 implementation days and <=2 correction cycles; split config/UI, retrieval/synthesis, persistence/callback, refresh/reaction, fetch/summarization and cleanup/deletion changes.

Approval checklist: default lenses; profile/project config and active set; raw-question policy; persistent proposal migration; refresh/reaction schedule/timezone/rates; provider budget/egress; live fetch/trusted hosts; four-week validation; release claim; compatibility cleanup; public examples. This roadmap grants none.

## Deep-review gates

The authoritative execution procedure is `docs/REVIEW_POLICY.md` and the
Playbook audit protocol. PRM-MAT closes batched review blocks after A (MAT-1…5),
B (MAT-6/7/11), C (MAT-8/9), D (MAT-10/12), E (MAT-13…16), before MAT-17, and
after MAT-18. High-risk changes can trigger an immediate review before their
block closes. Where the Playbook calls for an exec reviewer, the requested
reviewer is `gpt-5.6-terra` with `high` reasoning; the resulting audit must
record the effective runtime assignment rather than assuming it.
