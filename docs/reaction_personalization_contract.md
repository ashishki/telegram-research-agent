# Reaction Personalization Contract

Contract version: `reaction_personalization.v1`
Status: `implemented_and_verified` (`IRX-3`; 2026-07-13)
Applies to: Weekly Intelligence Brief V2, Knowledge Atlas V2, Editorial
Intelligence input, and Knowledge Audit Explorer

This contract defines how a personal Telegram reaction becomes a bounded,
auditable interest signal. It does not turn emoji into a durable preference,
evidence of truth, or permission to alter a project, profile, configuration, or
Radar decision.

## Product Outcome

The operator must be able to see whether reactions affected the report without
reading database rows or ranking traces. The system must be able to explain the
complete lineage:

```text
visible personal reaction
  -> stored raw Telegram post
  -> normalized source post
  -> Knowledge Atom
  -> current compatibility Idea Thread
  -> optional canonical Idea Thread (IRX-4)
  -> weak ranking boost
  -> selected signal/action/study item
  -> reader-facing effect receipt
```

The audited W29 reports stopped after loading marked posts into a separate
context list. IRX-3 now performs the deterministic report-time projection,
bounded selection influence, and consumed/unconsumed receipt. IRX-4 now
supplies stable canonical thread identity and historical as-of lineage through
the same nullable resolver contract without changing these semantics.

## Normative Semantics

The following rules are mandatory:

1. Any reaction that the Telegram API identifies as belonging to the operator
   is **positive implicit interest**.
2. The raw emoji is provenance metadata only. Different emoji do not encode
   different interest strength or sentiment.
3. Aggregate channel reaction counts are not personal feedback and must not be
   consumed.
4. No visible personal reaction means **unknown**, never disinterest or a
   negative score.
5. Several emoji from the operator on one post produce one post-level interest
   signal. They must not multiply the boost.
6. Interest is weak, bounded, time-sensitive, and subordinate to evidence
   quality and confirmed explicit report feedback.
7. A reaction cannot increase claim confidence, evidence maturity, source
   independence, project confidence, or Radar evidence.
8. A reaction cannot move an item through an evidence or safety gate. It may
   only help rank otherwise eligible items.
9. A single reaction cannot create or permanently update a standing operator
   profile, project descriptor, source policy, prompt, or configuration.
10. Every applied boost must be traceable; every reaction that is not consumed
    must have a machine-readable reason.

`operator_marked_interesting` is the current canonical feedback value.
`marked_important` remains a supported compatibility alias during migration.
Neither value is equivalent to confirmed report feedback such as `useful`,
`wrong_priority`, or `applied_to_project`.

## Time And Eligibility

The reaction projection consumes the same half-open UTC interval as the weekly
run:

```text
analysis_period_start <= source_post.posted_at < analysis_period_end
```

For a completed-week Weekly Brief, a reaction is eligible when all of these are
true:

- the run manifest's reaction-sync stage produced a usable snapshot before
  deterministic ranking;
- the reaction is visibly attributable to the operator in that snapshot;
- the normalized post can be resolved;
- the source post belongs to the run's analysis period;
- at least one Knowledge Atom cites that post through `source_post_ids`;
- at least one cited atom maps through `idea_thread_atoms` to an eligible current
  compatibility thread;
- the candidate signal still passes evidence, freshness, duplication, and
  editorial eligibility rules.

Telegram does not provide a reliable reaction-created timestamp in the current
pipeline. Therefore eligibility is based on the **source post period** and the
run's observed reaction snapshot, not `signal_feedback.recorded_at`. A reaction
on a Sunday post that is first synchronized during the Monday run is eligible
for the completed-week report. Reader copy must say it was detected on a source
post from the period; it must not claim the operator reacted at a particular
time.

Reactions on source posts outside the analysis period do not boost that Weekly
Brief. They may contribute, with decay, to cumulative operator-interest views
in Knowledge Atlas V2. This cumulative use must be reported separately and must
not be presented as a current-week effect.

If the run cannot attest current reaction visibility, old materialized sync rows
must not be silently presented as a fresh receipt. The run becomes partial for
reaction personalization. Loss or removal of a reaction never creates a
negative signal; it only removes eligibility for a fresh positive boost.

## Ranking Contract

Selection precedence is:

1. hard evidence, safety, period, and Radar gates;
2. deterministic evidence strength, source quality/independence, freshness, and
   change magnitude;
3. confirmed explicit report feedback;
4. bounded implicit reaction interest;
5. stable deterministic tie-breakers.

The implemented contribution is a single bounded adjacent promotion between
otherwise equal eligible candidates inside the exact reader selector. It cannot
cross stronger evidence or confirmed-feedback ordering, and cannot rescue weak,
stale, contradicted, superseded, or uncited evidence. A confirmed explicit
correction or negative priority signal wins over an implicit positive reaction
on the same target.

The counterfactual result must be retained:

- `boost_applied`: an eligible resolved current thread received the weak boost;
- `rank_changed`: the boost changed deterministic order;
- `selection_changed`: the boost changed which bounded report item appeared;
- `linked_only`: a selected item was related to a reaction, but would have been
  selected without the boost.

Only `rank_changed` or `selection_changed` may be described as an effect on
ranking. `linked_only` must not be overstated as causation.

## Mapping And Attribution

The deterministic projection must use stored identities, not semantic keyword
matching:

| Stage | Required join/provenance | Failure behavior |
|---|---|---|
| Reaction -> raw post | `channel_username` plus Telegram `message_id` | `post_not_found` |
| Raw post -> normalized post | `posts.raw_post_id` | `post_not_found` |
| Post -> atom | post ID in `knowledge_atoms.source_post_ids_json` | `knowledge_atom_not_extracted` |
| Atom -> current compatibility thread | `idea_thread_atoms.atom_id` and stored relation | `no_thread_link` |
| Current thread -> canonical thread | optional resolver result; registry/alias from IRX-4 | `no_canonical_thread_link` when canonical identity is required |
| Thread -> candidate | report candidate and evidence validation | eligibility reason |
| Candidate -> report item | versioned deterministic ranking trace | selected, duplicate, or limit reason |

One reacted post may cite several atoms and threads. All valid links remain in
the audit trace, but each resolved thread receives at most one post-level boost
per source post. IRX-3 emits `compatibility_thread_ref`, `current_thread_ref`, a
nullable `canonical_thread_ref`, and an explicit resolution status. IRX-4
preserves the original atom/post provenance when it adds alias, merge, split,
and historical as-of resolution.

The strong-model editorial pass may read the summarized effect trace. It may
explain the effect in Russian, but it may not invent a mapping, adjust the boost,
or decide that an unlinked reaction was consumed.

## Effect Receipt JSON

When an IRX-2 manifest binds a rich verified reaction snapshot, every succeeded
Brief and Atlas sidecar contains a validated `reaction_effect`; the two receipts
share run/period/snapshot/policy identity, pre-selection funnel counts, and
non-selection attribution. They may differ in `surface`, status, selected
items/counts, counterfactuals, and selector-dependent unconsumed results. A
legacy count-only reaction stage remains explicitly unbound/unavailable,
creates no fresh boost, and does not make a receipt mandatory. Brief classifies
against its four-item learning-action selector. Atlas classifies against its
twelve-item ranked thread-navigation selector. Both use exact
`surface_item_ref="thread:<slug>"` identities. The manifest binds the same-run
snapshot reference and validates the receipt against snapshot post/reaction
lineage; opaque post, reaction, atom, thread, and rank references remain in JSON
and retrieval/audit projections.

```json
{
  "schema_version": "reaction_personalization.v1",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "surface": "weekly_brief",
  "reporting_week": "2026-W28",
  "analysis_period_start": "2026-07-06T00:00:00Z",
  "analysis_period_end": "2026-07-13T00:00:00Z",
  "snapshot_ref": "reaction-snapshot:tra-weekly-2026-W28-20260713T070252Z",
  "snapshot_status": "complete",
  "status": "effects_applied",
  "counts": {
    "personal_reaction_events_detected": 5,
    "unique_reacted_posts": 5,
    "posts_resolved": 5,
    "eligible_period_posts": 2,
    "unique_atoms_linked": 2,
    "unique_canonical_threads_linked": 0,
    "canonical_threads_boosted": 0,
    "unique_compatibility_threads_linked": 1,
    "compatibility_threads_boosted": 1,
    "selected_items_linked": 1,
    "selected_signals_influenced": 1,
    "unconsumed_reaction_events": 3
  },
  "influenced_items": [
    {
      "surface_item_ref": "thread:agent-evaluation-discipline",
      "effect": "selection_changed",
      "reacted_post_count": 2,
      "compatibility_thread_ref": "idea_thread:agent-evaluation-discipline",
      "current_thread_ref": "idea_thread:agent-evaluation-discipline",
      "canonical_thread_ref": null,
      "thread_resolution_status": "compatibility_current_thread_only",
      "boost_role": "weak_implicit_interest",
      "reader_reason_ru": "Вы отметили 2 связанных поста за отчётный период.",
      "reacted_post_refs": [
        "reaction-post:111111111111111111111111",
        "reaction-post:222222222222222222222222"
      ],
      "source_refs": ["telegram:@ai_lab"],
      "boost_applied": true,
      "rank_changed": true,
      "selection_changed": true,
      "linked_only": false,
      "evidence_refs": ["atom:1282", "atom:1289"]
    }
  ],
  "linked_only_items": [],
  "eligible_thread_audit": [
    {
      "surface_item_ref": "thread:agent-evaluation-discipline",
      "reacted_post_count": 2,
      "compatibility_thread_ref": "idea_thread:agent-evaluation-discipline",
      "current_thread_ref": "idea_thread:agent-evaluation-discipline",
      "canonical_thread_ref": null,
      "thread_resolution_status": "compatibility_current_thread_only",
      "boost_role": "weak_implicit_interest",
      "reader_reason_ru": "Вы отметили 2 связанных поста за отчётный период.",
      "reacted_post_refs": [
        "reaction-post:111111111111111111111111",
        "reaction-post:222222222222222222222222"
      ],
      "source_refs": ["telegram:@ai_lab"],
      "evidence_refs": ["atom:1282", "atom:1289"],
      "selected": true,
      "counterfactual_effect": "selection_changed",
      "boost_applied": true
    }
  ],
  "unconsumed_by_reason": {
    "outside_analysis_period": 3
  },
  "unconsumed": [
    {
      "reaction_ref": "reaction:333333333333333333333333",
      "reason": "outside_analysis_period",
      "reasons": ["outside_analysis_period"],
      "audit_detail": "source post timestamp falls outside the half-open analysis period"
    },
    {
      "reaction_ref": "reaction:444444444444444444444444",
      "reason": "outside_analysis_period",
      "reasons": ["outside_analysis_period"],
      "audit_detail": "source post timestamp falls outside the half-open analysis period"
    },
    {
      "reaction_ref": "reaction:555555555555555555555555",
      "reason": "outside_analysis_period",
      "reasons": ["outside_analysis_period"],
      "audit_detail": "source post timestamp falls outside the half-open analysis period"
    }
  ],
  "ranking_policy": {
    "policy_version": "reaction-ranking.v1",
    "strength": "weak",
    "below_confirmed_feedback": true,
    "can_change_evidence_gate": false
  },
  "reader_summary_ru": "5 личных реакций → 5 постов найдено → 2 атомов знаний → 1 тем → 1 сигналов изменили позицию."
}
```

The example IDs above belong in JSON/audit detail, not visible reader copy.
Counts are deduplicated at the named entity level. Because one post may map to
multiple atoms, the lineage visualization is not a percentage-conversion claim.

Allowed top-level `status` values are:

- `effects_applied`;
- `linked_no_selection_effect`;
- `no_eligible_reactions`;
- `partial`;
- `unavailable`.

`no_eligible_reactions` is an unknown-interest state. It is not a failed sync
and not evidence that the operator disliked the week's subjects.

## Unconsumed Reasons

The machine-readable reason vocabulary is:

| Reason | Meaning |
|---|---|
| `post_not_found` | Telegram identity did not resolve to a normalized post |
| `outside_analysis_period` | source post is outside the Brief period |
| `knowledge_atom_not_extracted` | no source-backed atom cites the post |
| `no_thread_link` | atom has no raw Idea Thread membership |
| `no_canonical_thread_link` | IRX-4 registry cannot resolve a canonical thread |
| `stale_or_low_confidence_evidence` | linked item fails minimum evidence/freshness |
| `contradicted_or_retracted_evidence` | linked evidence is not eligible for promotion |
| `duplicate_signal` | stronger equivalent signal already represents the idea |
| `superseded_by_confirmed_feedback` | explicit confirmed feedback controls ordering |
| `report_limit_reached` | eligible item falls below the three-signal/action limits |
| `confirmed_feedback_snapshot_unverified` | current reaction visibility is complete but the run's confirmed-feedback context cannot be attested |
| `snapshot_unverified` | current personal visibility cannot be attested |

When several reasons apply, record all in the audit trace and choose the first
applicable reason in the table as the primary count. This makes aggregate counts
stable. Reader surfaces summarize reasons in Russian and do not expose enum
values or identifiers.

## Reader Presentation

Weekly Brief V2 shows one compact reaction funnel and card-level receipts. The
funnel is lineage, not proof of claim quality.

Example complete state:

> **Как реакции повлияли на бриф**
>
> 18 личных реакций -> 15 постов найдено -> 11 атомов знаний -> 6 тем -> 3
> сигнала изменили позицию в брифе.

Example card receipt:

> **Почему этот сигнал здесь:** вы отметили два связанных поста за отчётный
> период. Сигнал всё равно прошёл проверку доказательств.

Example linked-only state:

> Ваши отметки связаны с этой темой, но не изменили её место: сигнал уже входил
> в тройку по силе доказательств.

Example no-reaction state:

> Для источников этого периода личные реакции не найдены. Это не снижало оценки
> тем и не трактовалось как отсутствие интереса.

Example partial state:

> Синхронизация реакций не завершена. Персонализация по реакциям для этого
> запуска не применялась.

The reader receipt may show counts, Russian explanations, and links to selected
signals. Raw emoji, database IDs, canonical IDs, boost values, joins, and
ranking traces belong under `Технические детали` in the Knowledge Audit
Explorer.

## Repeated Patterns And Standing Preferences

An individual reaction expires as a weekly ranking signal after its applicable
period. A repeated pattern may become a Strategy Reviewer **proposal**, never an
automatic preference.

Strategy Reviewer may suggest a standing profile/config change only when the
same resolved interest pattern appears in at least three distinct completed
weeks within a rolling 12-week window and is supported by at least four distinct
reacted posts. Before IRX-4 this pattern is explicitly compatibility-thread
attribution, not a claim of stable canonical identity. The proposal must include:

- resolved compatibility/canonical pattern refs and aliases involved;
- weeks, post count, and source diversity;
- decay/recency information;
- confirmed feedback that supports or contradicts the pattern;
- the exact proposed profile/config delta;
- expected report effect and rollback path;
- an expiry or review date.

A temporary curiosity spike, several emoji on one post, or several posts in one
week cannot satisfy the threshold. Confirmed explicit feedback remains stronger
than the reaction pattern.

The proposal enters the existing confirmation-gated feedback/strategy flow.
Only explicit operator approval may persist a standing profile, source policy,
project descriptor, prompt, or config change. Rejection or deferral leaves the
current configuration unchanged. Code changes always remain a separate,
operator-approved engineering task.

Reader-facing example:

> **Предложение Strategy Reviewer:** интерес к дисциплине агентной разработки
> повторился в 3 из 12 недель. Изменение профиля не применено. Подтвердите или
> отклоните предложение отдельно.

## Failure States

| Failure | Required behavior |
|---|---|
| Reaction sync fails or is stale | manifest/report partial; no fresh boost; visible Russian notice |
| Aggregate counts cannot prove operator identity | ignore as feedback; audit reason |
| Post cannot be resolved | no boost; `post_not_found` |
| Atom/thread link is absent | no semantic guessing; record the mapping reason |
| Canonical registry is unavailable | no raw entity-cluster boost presented as canonical |
| Ranking trace is missing | no claim that a reaction affected selection |
| Receipt and ranking disagree | fail personalization quality gate |
| Explicit feedback conflicts with reaction | explicit confirmed feedback wins; conflict audited |
| Editorial model invents an effect | schema/evidence validation rejects output; report partial |
| No reactions exist | unknown state; no penalty; not a pipeline failure |

## Compatibility And Rollout

- Reuse `reaction_sync_state`, `signal_feedback`, `user_post_tags`, normalized
  post identities, `knowledge_atoms.source_post_ids_json`, and
  `idea_thread_atoms`.
- Add the V2 projection and receipt without changing V1 sidecar meaning during
  migration.
- Keep `operator_marked_interesting` and the historical `marked_important`
  alias readable.
- Keep raw provenance accessible to Hermes/PI and the Knowledge Audit Explorer;
  provide V1/V2 retrieval adapters before changing sidecar consumers.
- Do not require a new source, vector retrieval, raw Telegram RAG, or a global
  regeneration of knowledge.
- IRX-3 depends on IRX-1 period resolution and the IRX-2 reaction snapshot/run
  identity. Its additive thread-resolution interface exposes current
  compatibility refs and nullable canonical refs without relabelling raw entity
  clusters as canonical. IRX-4 supplies the stored registry, merge/split
  aliases, and period-end as-of lineage; the ranking and receipt boundary
  itself remains unchanged.
- IRX-5 consumes only the validated summary. IRX-6 and IRX-7 render it. IRX-11
  validates receipt presence and agreement. IRX-12 remains the stronger,
  confirmation-gated explicit feedback path.

## Implementation Files And Compatibility Adapters

- `src/ingestion/reaction_sync.py`
- `src/output/reaction_personalization.py`
- `src/output/ai_intelligence_report.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/knowledge_atlas_report.py`
- `src/output/split_intelligence_reports.py`
- `src/output/weekly_intelligence_orchestrator.py`
- `src/output/weekly_run_manifest.py`
- `src/output/intelligence_retrieval_items.py`
- `src/output/strategy_reviewer.py`
- `src/output/obsidian_export.py`
- `src/assistant/pi_facade.py`
- `src/main.py`
- focused reaction, report, manifest/orchestrator, Strategy Reviewer, retrieval,
  and PI tests

## Acceptance And Test Matrix

IRX-3 is accepted only when all of the following are demonstrated:

- any personal emoji fixture creates one positive post-level interest signal;
- aggregate-only reactions create none;
- no reaction leaves ranking unchanged and records unknown, not negative;
- two emoji on one post do not multiply the boost;
- a Sunday source post first synchronized by Monday's run influences the
  completed-week candidate set;
- a post outside the analysis period is not used by that Brief;
- post -> atom -> current compatibility thread provenance uses stored
  identities, with the missing canonical/as-of link explicit;
- an otherwise equal eligible item receives the bounded reaction boost;
- weak/stale evidence cannot be rescued by a reaction;
- confirmed report feedback overrides a conflicting implicit reaction;
- `boost_applied`, `rank_changed`, and `selection_changed` are distinguished by
  counterfactual assertions;
- all unconsumed reason paths produce stable counts;
- JSON and HTML contain the same effect totals;
- reader copy is Russian and contains no raw IDs, enums, or ranking values;
- sync failure produces a partial receipt and visible partial state;
- a repeated pattern below the three-week/four-post threshold creates no
  Strategy Reviewer proposal;
- a qualifying repeated pattern creates an unapproved proposal only, and no
  standing profile/config value changes until explicit confirmation;
- V1 retrieval, Hermes/PI, and Obsidian compatibility tests continue to pass.

Focused verification commands used for implementation:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_reaction_personalization \
  tests.test_reaction_sync tests.test_ai_intelligence_report \
  tests.test_ai_report_feedback tests.test_strategy_reviewer \
  tests.test_split_intelligence_reports \
  tests.test_intelligence_retrieval_items tests.test_pi_facade
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_weekly_run_manifest \
  tests.test_weekly_intelligence_orchestrator
git diff --check
```

Focused verification passed on 2026-07-13: 145 tests in the core
reaction/report/feedback/Strategy/split/retrieval/PI matrix and 45 tests in the
manifest/orchestrator matrix. `git diff --check` passed; live/heavy pipelines
and the full suite were intentionally not run.

## IRX-3 Implementation Receipt - 2026-07-13

- Only a complete, current, checksum- and identity-validated same-run IRX-2
  snapshot can create fresh interest. Partial, unavailable, stale, truncated,
  wrong-period, or tampered inputs fail closed; an unattested feedback snapshot
  produces a distinct partial receipt and no boost.
- Every operator-visible emoji is equivalent positive provenance. Events are
  deduplicated to one weak signal per post; aggregate reactions are ignored and
  absence remains unknown.
- Attribution uses stored Telegram channel/message identity through raw and
  normalized posts, bounded atoms, and `idea_thread_atoms`. Opaque lineage refs,
  full eligible-thread audit, bounded unconsumed samples, funnel counts, and
  counterfactual effects are strictly validated.
- Brief and Atlas classify the same personalized order against their exact
  four-action and twelve-thread selectors and emit surface-specific receipts
  whose common identity, pre-selection funnel, non-selection attribution,
  snapshot lineage, and policy must agree. Within each surface, its own JSON and
  HTML totals must agree; selector-dependent status, selected counts,
  counterfactuals, and unconsumed results may legitimately differ.
- Evidence/safety/freshness/deduplication gates and confirmed explicit feedback
  remain stronger. The weak reaction marker performs at most one adjacent
  promotion among otherwise equal eligible items and never changes global
  scoring, evidence confidence, feedback semantics, or Radar gates.
- Repeated interest can only create an unapproved, advisory Strategy Reviewer
  proposal after three completed weeks and four distinct posts. It never mutates
  profile, config, prompt, project, source policy, or code.
- Existing standalone/V1 output, legacy reaction-sync return values and tag
  aliases, Brief/Atlas contexts, Hermes/PI, retrieval, and Obsidian consumers
  remain compatible through additive fields/adapters. No database schema,
  prompt, generated report, or cross-repository code change was required.
- IRX-4 implements the durable canonical registry and historical period-end
  as-of thread lineage. IRX-3 still does not claim that current compatibility
  threads are stable canonical threads: stored canonical resolution is
  separate and nullable, and raw refs/provenance remain present.

## Stop Conditions

Stop and ask the operator before implementing or proposing a design that:

- treats reaction absence as negative;
- assigns permanent semantic meaning or different score strength to emoji;
- turns one reaction or an unconfirmed repeated pattern into a standing
  preference;
- lets reaction interest weaken evidence, safety, or Radar gates;
- lets context-only Radar data become evidence through personalization;
- uses broad keyword matching instead of post/atom/thread provenance;
- lets a model invent reaction links or effect claims;
- applies profile, config, prompt, project, or code changes without explicit
  approval;
- breaks existing Hermes/PI, Obsidian, or V1 sidecar retrieval without an
  additive migration plan.
