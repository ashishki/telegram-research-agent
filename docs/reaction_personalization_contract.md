# Reaction Personalization Contract

Contract version: `reaction_personalization.v1`  
Status: planned (`IRX-3`; not implemented)  
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
  -> normalized source post
  -> Knowledge Atom
  -> canonical Idea Thread
  -> weak ranking boost
  -> selected signal/action/study item
  -> reader-facing effect receipt
```

The W29 reports stop after loading marked posts into a separate context list.
They do not perform the atom/thread projection, do not apply a selection boost,
and do not show consumed or unconsumed effects. Existing ingestion is reusable;
the missing capability is the report-time projection and receipt.

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
- at least one cited atom maps through `idea_thread_atoms` to an active canonical
  thread;
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

IRX-3 may choose a numeric implementation only if it preserves this order. The
reaction contribution must be capped so that it can break a close comparison
between eligible candidates but cannot rescue weak, stale, contradicted, or
uncited evidence. A confirmed explicit correction or negative priority signal
wins over an implicit positive reaction on the same target.

The counterfactual result must be retained:

- `boost_applied`: an eligible canonical thread received the weak boost;
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
| Atom -> raw thread | `idea_thread_atoms.atom_id` | `no_thread_link` |
| Raw thread -> canonical thread | canonical registry/alias from IRX-4 | `no_canonical_thread_link` |
| Thread -> candidate | report candidate and evidence validation | eligibility reason |
| Candidate -> report item | versioned deterministic ranking trace | selected, duplicate, or limit reason |

One reacted post may cite several atoms and threads. All valid links remain in
the audit trace, but each canonical thread receives at most one boost per source
post. Alias, merge, and split resolution must preserve the original atom and
post provenance.

The strong-model editorial pass may read the summarized effect trace. It may
explain the effect in Russian, but it may not invent a mapping, adjust the boost,
or decide that an unlinked reaction was consumed.

## Effect Receipt JSON

Every Brief V2 sidecar contains `reaction_effect`; Atlas V2 contains the same
schema with `surface="knowledge_atlas"`. The manifest holds the snapshot
reference, while raw post, atom, thread, and rank identifiers remain in the
Audit Explorer or audit sidecar.

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
    "personal_reaction_events_detected": 18,
    "unique_reacted_posts": 15,
    "posts_resolved": 15,
    "eligible_period_posts": 13,
    "unique_atoms_linked": 11,
    "unique_canonical_threads_linked": 6,
    "canonical_threads_boosted": 6,
    "selected_items_linked": 3,
    "selected_signals_influenced": 3,
    "unconsumed_reaction_events": 3
  },
  "influenced_items": [
    {
      "surface_item_ref": "signal:agent-evaluation-discipline",
      "effect": "selection_changed",
      "reacted_post_count": 2,
      "canonical_thread_ref": "agentic-engineering-production-discipline",
      "boost_role": "weak_implicit_interest",
      "reader_reason_ru": "Вы отметили два связанных поста за период.",
      "evidence_refs": ["atom:1282", "atom:1289"]
    }
  ],
  "linked_only_items": [],
  "unconsumed_by_reason": {
    "outside_analysis_period": 2,
    "report_limit_reached": 1
  },
  "unconsumed": [
    {
      "reaction_ref": "reaction:opaque-audit-ref",
      "reason": "outside_analysis_period",
      "audit_detail": "source post timestamp precedes analysis_period_start"
    }
  ],
  "ranking_policy": {
    "policy_version": "reaction-ranking.v1",
    "strength": "weak",
    "below_confirmed_feedback": true,
    "can_change_evidence_gate": false
  }
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
same canonical interest pattern appears in at least three distinct completed
weeks within a rolling 12-week window and is supported by at least four distinct
reacted posts. The proposal must include:

- canonical threads and aliases involved;
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
  identity. It establishes a thread-resolution interface before IRX-4, so the
  post/atom projection and bounded boost can be implemented in priority order.
  IRX-4 then supplies the canonical registry; until that registry is available,
  reader-facing thread attribution remains partial rather than pretending raw
  entity clusters are canonical.
- IRX-5 consumes only the validated summary. IRX-6 and IRX-7 render it. IRX-11
  validates receipt presence and agreement. IRX-12 remains the stronger,
  confirmation-gated explicit feedback path.

## Likely Implementation Files

- `src/ingestion/reaction_sync.py`
- `src/output/ai_intelligence_report.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/knowledge_atlas_report.py`
- a new deterministic reaction projection helper under `src/output/`
- `src/db/ai_report_feedback.py` only where an additive projection/adapter is
  necessary
- `src/output/report_quality.py`
- `src/output/split_intelligence_reports.py`
- `tests/test_reaction_sync.py`
- report-ranking, split-report, quality, and retrieval compatibility tests

## Acceptance And Test Matrix

IRX-3 is accepted only when all of the following are demonstrated:

- any personal emoji fixture creates one positive post-level interest signal;
- aggregate-only reactions create none;
- no reaction leaves ranking unchanged and records unknown, not negative;
- two emoji on one post do not multiply the boost;
- a Sunday source post first synchronized by Monday's run influences the
  completed-week candidate set;
- a post outside the analysis period is not used by that Brief;
- post -> atom -> canonical thread provenance uses stored identities;
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

Focused verification commands for implementation:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_reaction_sync.py tests/test_ai_intelligence_report.py
PYTHONPATH=src python3 -m pytest -q \
  tests/test_split_intelligence_reports.py \
  tests/test_intelligence_retrieval_items.py tests/test_pi_facade.py
rg -n "reaction_effect|operator_marked_interesting|no_eligible_reactions" src tests
```

The implementation must add focused ranking/receipt tests rather than relying
only on the existing ingestion tests.

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
