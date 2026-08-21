# PRM Local Deep Research Review - 2026-08-21

Status: implemented for manual runtime; not dogfood evidence
Scope: bounded local `archive_to_action` research only

## Trigger

Real operator feedback showed that citation presence and FTS/vector provenance
were insufficient: answers could contain only partial or promotional material
and still fail to produce a useful, evidence-backed action.

## Reviewed design

The reviewed flow is `plan -> gather -> gap-check -> synthesise -> verify`.
It is implemented by `assistant.memory_research`, `prm.research_planner`, and
the PRM application boundary.

## Findings and disposition

| Finding | Disposition |
| --- | --- |
| Initial top-N results can hide useful practice | Gather up to 32 local candidates across bounded variants |
| Topic matches can be promotions or model comparisons | Source-role classification remains ahead of applicability |
| Partial context does not justify an action | Gap check requests one targeted local practice-search wave |
| Provider output could invent source selection | Provider receives cited excerpts and may return supplied IDs only |
| Provider outage must not block research | Deterministic role-aware fallback is retained |
| Full archive context would violate privacy and cost bounds | Raw corpus remains excluded; 12 short cited excerpts are the provider maximum |

## Verification evidence

- focused planner, application, memory-research, archive-contract, retrieval,
  feedback-receipt, and Telegram callback suites passed; the pre-existing
  date-sensitive fixture and contradictory keyboard expectation were deselected;
- Python compilation of changed modules passed;
- diff whitespace validation passed;
- validation used synthetic/local fixtures only; it did not run production
  archive mutation, ingestion, reaction sync, external embedding, hosted
  vector, or dogfood activity.

## Residual risks

- Deterministic source-role markers require further calibration against operator
  feedback and can still classify a terse useful post as context.
- The optional provider reranker is not an independent judge; its selection is
  constrained but needs measured comparison against a human-reviewed holdout.
- Current feedback contains useful and negative examples but is not sufficient
  to claim a product-quality improvement rate.
- Telegram callback acknowledgement errors are operationally separate from
  research quality and remain a follow-up item.

## Completion boundary

This record does not claim dogfood start, release readiness, external research
capability, or adoption of the referenced external stack. It records a local,
bounded implementation slice only.
