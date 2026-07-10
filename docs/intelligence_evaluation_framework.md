# Intelligence Evaluation Framework

Version: 1.0
Last updated: 2026-07-10
Status: supporting specification for `docs/portfolio_grade_intelligence_roadmap.md`

This document defines the evaluation layers required before the system can make
portfolio-grade claims. Structural tests are useful but insufficient: the system
must also measure evidence correctness, relevance, decisions, learning,
assistant grounding, Radar honesty, and usability.

Notation per layer:

- U: unit of evaluation.
- O: expected output.
- GT: ground truth source.
- A: annotation protocol.
- Off: offline metrics.
- On: online/dogfood metrics.
- Data: minimum dataset.
- Fail: required failure cases.
- Fix: regression fixture.
- Review: review frequency.
- Cost: human annotation cost.
- Threshold: provisional acceptance threshold; final thresholds require a
  four-week baseline.

## Evaluation Layers

1. Source normalization
   - U: one ingested source observation. O: normalized source type, URL,
     timestamp, excerpt, metadata, collection method. GT: raw Telegram/source
     fixture. A: one reviewer checks field preservation and redaction. Off:
     field completeness, URL validity, timestamp parse rate. On: missing-source
     incidents. Data: 100 observations across Telegram/Radar fixtures. Fail:
     missing URL, wrong timestamp, private text leak. Fix: source normalization
     fixture. Review: monthly. Cost: low. Threshold: no P0 privacy/provenance
     failures; completeness target set after baseline.
2. Evidence extraction
   - U: one candidate evidence item. O: quote/excerpt, role, tier,
     independence key, verification status, staleness. GT: source observation.
     A: reviewer marks whether excerpt supports the evidence role. Off:
     evidence precision, role accuracy, tier accuracy. On: weak-evidence
     feedback. Data: 50 positive, 25 negative/contradictory items. Fail:
     market commentary promoted to demand proof. Fix: evidence extraction
     fixture. Review: every PR touching extraction. Cost: medium. Threshold:
     no context-only item can pass as decision evidence.
3. Claim extraction
   - U: one claim. O: statement, scope, time horizon, support/contradiction
     refs, uncertainty. GT: evidence item set. A: reviewer checks atomicity and
     support. Off: support precision, unsupported claim rate. On: trust
     corrections. Data: 60 claims. Fail: summary sentence treated as claim;
     claim broader than evidence. Fix: claim extraction fixture. Review:
     weekly during Phase 1. Cost: medium. Threshold: unsupported top-claim
     rate must trend to zero before portfolio demo.
4. Quote verification
   - U: one quote or excerpt. O: verified/unverified with source span or
     explicit weak label. GT: raw source text. A: deterministic exact/near-match
     plus spot review. Off: verified quote coverage, false verification rate.
     On: false-confidence incidents. Data: top 20 quotes per fixture week.
     Fail: paraphrase labeled as exact quote. Fix: quote verification fixture.
     Review: every report-contract change. Cost: low. Threshold: top-claim
     verified quote coverage target is 100%.
5. Atom atomicity
   - U: one Knowledge Atom. O: one useful knowledge change, source refs,
     staleness. GT: evidence/claim set. A: reviewer splits/merges atoms as
     needed. Off: multi-claim atom rate, duplicate atom rate. On: Atlas
     confusion feedback. Data: 100 atoms across two weeks. Fail: broad weekly
     summary stored as atom. Fix: atom fixture. Review: biweekly. Cost: medium.
     Threshold: baseline needed.
6. Atom usefulness
   - U: one atom surfaced in Brief/Atlas. O: reason it matters, operator
     relevance, expiry. GT: manual usefulness labels and outcomes. A: operator
     labels useful/too shallow/wrong priority. Off: usefulness precision.
     On: useful/tried/applied rates. Data: 40 surfaced atoms. Fail: interesting
     but unactionable atom promoted. Fix: usefulness fixture. Review: weekly.
     Cost: low-medium. Threshold: precision target set after four weeks.
7. Thread grouping
   - U: one atom-to-thread assignment. O: thread slug, relation, rationale. GT:
     reviewer grouping. A: reviewer marks same idea, adjacent idea, or wrong.
     Off: grouping precision, over-merge rate, split-needed rate. On: Atlas
     thread-understanding task success. Data: 150 assignments. Fail: hype terms
     merge unrelated claims. Fix: thread grouping fixture. Review: monthly.
     Cost: medium. Threshold: over-merge incidents must be visible, not hidden.
8. Thread merge/split
   - U: one thread continuity change. O: merge/split audit, previous/current
     state. GT: thread history and reviewer audit. A: reviewer approves or
     requests split. Off: suspicious continuity rate, corrected merge/split
     rate. On: stale/confused thread feedback. Data: 20 changed threads. Fail:
     new technology fork overwrites prior state. Fix: merge/split fixture.
     Review: monthly. Cost: medium. Threshold: no silent merge for top threads.
9. Novelty detection
   - U: one surfaced change. O: new, repeated, resurfaced, or stale. GT: prior
     thread/atom history. A: reviewer checks against last 90 days. Off: novelty
     precision, repeated-as-new rate. On: ignored-but-repeated topic rate. Data:
     two rolling weeks plus 90-day history sample. Fail: old topic announced as
     new. Fix: novelty fixture. Review: weekly. Cost: low-medium. Threshold:
     baseline needed.
10. Temporal delta
    - U: one thread delta. O: previous state, new evidence, updated
      interpretation, confidence movement. GT: prior/current source sets. A:
      reviewer checks delta causality. Off: delta support precision, missing
      previous-state rate. On: Brief "what changed" usefulness. Data: top 10
      deltas per week. Fail: momentum-only change framed as evidence growth.
      Fix: temporal delta fixture. Review: weekly. Cost: medium. Threshold:
      top deltas must cite new evidence or declare insufficient history.
11. Contradiction detection
    - U: one claim/thread. O: contradiction or no contradiction with evidence
      refs. GT: manually paired support/contradiction examples. A: reviewer
      labels contradiction, nuance, or unrelated. Off: contradiction recall and
      precision. On: contradiction visibility rating. Data: 30 contradiction
      pairs and 50 non-pairs. Fail: negative evidence hidden. Fix:
      contradiction fixture. Review: every Phase 1 PR. Cost: medium.
      Threshold: contradictions affecting top claims must be visible.
12. Source independence
    - U: evidence set for one claim/candidate. O: independence keys and source
      diversity. GT: source metadata and reviewer family labels. A: reviewer
      groups dependent reposts/same-origin sources. Off: independence precision,
      single-source overstatement. On: false-confidence incidents. Data: 40
      claims. Fail: copied Telegram reposts counted as independent. Fix:
      independence fixture. Review: monthly. Cost: medium. Threshold:
      build/apply claims cannot rely on fake independence.
13. Project relevance
    - U: one Project Implication. O: confirmed lead/watch/learning/rejected
      overlap. GT: project docs, code ownership, operator label. A: reviewer
      checks specific repo fit and evidence. Off: precision by tier, rejected
      overlap accuracy. On: project changes made, wrong-project rate. Data: 30
      implications across active repos. Fail: broad keyword match promoted.
      Fix: project relevance fixture. Review: weekly. Cost: medium. Threshold:
      confirmed leads require source-specific evidence.
14. Personal relevance
    - U: one ranked item. O: relevance factors and confidence. GT: explicit
      operator context and feedback outcomes. A: operator labels priority,
      saturation, novelty fit. Off: precision@3, precision@5, wrong-priority
      rate. On: useful/tried/applied/changed-decision rates. Data: 4 weekly
      ranked lists. Fail: read-only signal overrides explicit context. Fix:
      personal relevance fixture. Review: weekly. Cost: low. Threshold:
      provisional until dogfood baseline.
15. Ranking
    - U: ordered Brief/Atlas item list. O: ranked items with factor scores. GT:
      operator labels and outcomes. A: compare alternative rankings manually
      after the week. Off: nDCG, precision@k, calibration by confidence. On:
      clicked/read/useful/tried/applied. Data: 6 weekly lists preferred. Fail:
      low-evidence high-hype item ranked top. Fix: ranking fixture. Review:
      weekly. Cost: low-medium. Threshold: no unsupported top item.
16. Weekly synthesis
    - U: one Weekly Brief. O: decision snapshot, changes, evidence/trust,
      actions, ignore/defer, project/Radar/feedback blocks. GT: structured
      sidecar plus operator task review. A: reviewer completes 5-minute Brief
      task. Off: required-section pass, unsupported narrative rate. On: time to
      understand, decisions selected. Data: four weekly Briefs. Fail: Brief
      becomes Atlas or hides gaps. Fix: Brief usability fixture. Review: weekly.
      Cost: medium. Threshold: 5-minute target after baseline.
17. Recommendations
    - U: one action/decision recommendation. O: rationale, evidence, success,
      kill condition, follow-up. GT: outcome and source support. A: operator
      records decision/outcome next week. Off: recommendation support rate.
      On: completed actions, killed experiments, changed decisions. Data: 20
      recommendations. Fail: action counted useful without outcome. Fix:
      recommendation fixture. Review: weekly. Cost: low. Threshold: no action
      without success/kill condition.
18. Learning objectives
    - U: one Learning Objective. O: prerequisite, current state, exercise,
      project task, mastery evidence. GT: implementation/test/outcome artifacts.
      A: operator marks stage with evidence link. Off: stage consistency,
      prerequisite gap detection. On: concepts moved to implemented/tested.
      Data: 10 objectives. Fail: reading marked as mastery. Fix: learning
      objective fixture. Review: biweekly. Cost: low. Threshold: mastery needs
      implementation or evaluation evidence.
19. Project implications
    - U: one repo implication card. O: relevant signals, tiny PR, stale
      decisions, research debt. GT: repo files/tasks and operator label. A:
      reviewer checks whether a PR is realistic. Off: precision and acceptance
      criteria completeness. On: PRs opened/merged, stale decisions updated.
      Data: 20 cards. Fail: no-code idea framed as implementation lead. Fix:
      project implication fixture. Review: weekly. Cost: medium. Threshold:
      confirmed lead must produce PR-ready scope.
20. Hermes retrieval
    - U: one Hermes tool query. O: curated retrieval items only, filters,
      provenance. GT: sidecar/DB fixture. A: reviewer checks returned items.
      Off: hit@k, raw-firehose exclusion, citation coverage. On: answer
      satisfaction and follow-up success. Data: 50 queries. Fail: raw Telegram
      RAG used by default. Fix: Hermes retrieval fixture. Review: every Hermes
      PR. Cost: low-medium. Threshold: raw firehose status remains disabled.
21. Hermes grounded answer
    - U: one assistant answer. O: answer with source/provenance, uncertainty,
      insufficient-evidence state. GT: curated objects. A: reviewer labels
      grounded, partially grounded, unsupported. Off: groundedness, citation
      precision, refusal/insufficient accuracy. On: satisfaction, correction
      rate. Data: 40 answers. Fail: market commentary stated as proof. Fix:
      answer eval dataset. Review: every Hermes PR and weekly dogfood. Cost:
      medium. Threshold: no hidden mutation, no uncited factual claim.
22. Feedback parsing
    - U: one text/voice/button feedback event. O: proposed event, provenance,
      target, confirmation state. GT: operator intent label. A: reviewer labels
      parsed type and accidental/correction status. Off: type accuracy, target
      accuracy. On: correction frequency, friction. Data: 100 feedback samples.
      Fail: pending draft counted as memory. Fix: feedback parsing fixture.
      Review: monthly. Cost: low. Threshold: pending is never stored as
      confirmed feedback.
23. Feedback effect
    - U: one prior feedback event. O: effect window, ranking/context impact, or
      no effect reason. GT: sidecar diff and operator expectation. A: reviewer
      checks next-run explanation. Off: effect trace completeness, incorrect
      promotion rate. On: trust in personalization. Data: 40 events over four
      weeks. Fail: feedback claimed to affect already-generated artifact. Fix:
      feedback effect fixture. Review: weekly. Cost: low-medium. Threshold:
      every cited feedback effect has provenance and timing.

PGI-002 baseline fixtures now cover layers 14, 15, 22, and 23 for confirmed vs
pending feedback, append-only correction/retraction, no-feedback as `unknown`,
`read` as weak observation, feedback effect windows, and sidecar-backed
`ranking_factors`/`why_selected` HTML parity.

PGI-003 baseline fixtures now cover layers 16, 20, 21, 24, and 25 for Brief
decision cockpit structure, exact feedback targets, read-only Hermes artifact
awareness, missing/stale Radar warnings, market context as `context_only`, and
matched external evidence as the only Radar gate input.
24. Radar handoff
    - U: one Radar seed/context/dossier exchange. O: contract version, context
      markers, matched evidence, missing evidence, decision action. GT: Telegram
      sidecar and Radar JSON/Markdown. A: reviewer checks parity across repos.
      Off: contract compliance, context-only misuse count, stale artifact
      detection. On: Radar decision changes after validation. Data: four weekly
      exchanges. Fail: market context satisfies build gate. Fix: Radar handoff
      fixture. Review: every cross-repo change. Cost: medium. Threshold: zero
      context-only gate violations.
25. Brief usability
    - U: one Brief reading session. O: user completes key tasks in bounded time.
      GT: task checklist and operator log. A: timed manual task review. Off:
      structural checklist. On: time-to-understand, task success, feedback
      friction. Data: four weeks. Fail: cannot find action/evidence/Radar gap
      quickly. Fix: usability checklist fixture. Review: weekly. Cost: medium.
      Threshold: target after baseline; provisional goal is under 5 minutes.
26. Atlas usability
    - U: one Atlas navigation task. O: find source, understand thread, identify
      contradiction/open question. GT: Atlas sidecar and source refs. A: timed
      manual task review. Off: sidecar completeness. On: source-find success,
      thread-understanding success. Data: four weeks, at least three tasks per
      week. Fail: Atlas is static wall of text or decorative graph. Fix: Atlas
      usability fixture. Review: weekly during Phase 5. Cost: medium.
      Threshold: target after baseline.

## Weekly Intelligence Scorecard

Every dogfood week records a scorecard row. Do not fake precision before the
baseline exists; record actual values, `unknown`, or `not_measured`.

### Correctness

- provenance coverage for top claims;
- verified quote coverage;
- unsupported claim rate;
- single-source overstatement rate;
- contradiction visibility;
- false-confidence incidents.

### Relevance

- precision@3 personally useful topics;
- precision@5 read targets;
- wrong-priority rate;
- ignored-but-repeated topic rate;
- personalization confidence.

### Decisions And Actions

- time to understand;
- decisions changed;
- actions selected;
- actions completed;
- experiments completed;
- project changes made;
- defer/reject decisions captured.

### Learning

- concepts moved from read to implemented;
- skill gaps closed;
- exercises completed;
- stale knowledge revisited;
- learning linked to project evidence.

### UX

- Brief first-screen task success;
- Atlas find-source task success;
- Atlas understand-thread task success;
- Hermes answer satisfaction;
- feedback friction.

### Radar

- candidates with matched external evidence;
- context-only items incorrectly treated as evidence;
- decision changes after validation;
- stale/missing Radar incidents;
- contradictions between Radar JSON, Markdown, Brief, and Hermes.

### Operations

- report generation success;
- missing artifacts;
- cost;
- latency;
- test/eval regressions;
- health-check failures.

## Annotation Rules

- Use source excerpts, sidecars, and tests before reading generated prose.
- A reviewer can mark `not_enough_information`; do not force labels.
- Evidence labels are append-only. Corrections add a correction event.
- Private generated artifacts stay outside git unless sanitized.
- A weekly score is invalid if the Radar context-only rule or Hermes mutation
  boundary is violated.

## Current Regression Fixtures

PGI-001 adds sanitized canonical-contract fixtures under
`tests/fixtures/intelligence_contract/`:

- `valid_canonical_sidecar.json` for SourceObservation/EvidenceItem/Claim
  shape and source-bound decision-grade claims.
- `unsupported_decision_grade_claim.json` for unsupported top-claim failure.
- `context_only_radar_gate.json` for Radar context-only gate misuse.
