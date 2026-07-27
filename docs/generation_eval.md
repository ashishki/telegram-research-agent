# Generation Evaluation Plan

Status: draft; PRM-4 no-answer vertical slice recorded; PRM-10 grounded answer contract recorded
Last updated: 2026-07-26

## Scope

Evaluate assistant answers generated from retrieved Telegram archive and curated
knowledge evidence.

## Required Output Checks

- direct answer present;
- archive-supported claims cite Telegram links;
- unsupported model background is labelled as background;
- freshness boundary is explicit;
- contradictions or uncertainty are shown when present;
- external verification need is labelled;
- insufficient evidence is used when support is weak;
- no raw private corpus dump appears in logs or artifacts.

## PRM-4 Vertical Slice Evidence

PRM-4 does not claim full grounded answer generation quality. It verifies the
first assistant path from planned read-only archive search tool call to bounded
answer behavior.

Verified fixture behavior:

- exact archive search chat path calls `search_telegram_archive` and carries the
  Telegram source link into collected evidence;
- exact archive search answer includes the source link supplied by the tool;
- no-answer archive search path returns `insufficient_evidence`;
- no-answer fallback has no `source_refs` and does not fabricate a Telegram
  citation;
- fallback wording says evidence is missing or insufficient instead of filling
  gaps from model knowledge.

Verification command:

```bash
python3 -m pytest tests/test_pi_chat.py -q
```

Expected result in PRM-4 run:

```text
7 passed
```

## PRM-10 Grounded Answer Evidence

Implementation:

- `assistant.pi_chat.answer_pi_chat` now returns additive
  `answer_contract` and `telemetry` objects.
- `grounded_answer_contract.v1` includes direct answer, archive support,
  source links, uncertainty, freshness/date boundary, model background label,
  external verification need, optional next action, and
  `insufficient_evidence`.
- `pi_answer_telemetry.v1` separates planning, retrieval, and generation
  latency/cost/model-call fields, including whether costs came from a live
  completion receipt or a fake/unmetered test client.
- Unsupported answers without archive source links are labelled
  `model_background.label=background_not_archive_supported` and
  `archive_support.status=insufficient_evidence`.
- Telemetry privacy flags assert that raw post text, raw tool payloads, and
  provider payloads were not logged. Bounded snippet provider context is
  recorded separately from broad raw corpus egress.

Verification command:

```bash
python3 -m pytest tests/test_pi_chat.py tests/test_pi_tools.py tests/test_archive_search.py tests/test_archive_documents.py -q
```

Result:

```text
37 passed in 1.75s
python3 -m pytest tests/ -q
1 failed, 996 passed, 281 subtests passed in 248.15s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

## Metrics

- faithfulness;
- completeness;
- relevance;
- citation correctness;
- no-answer correctness;
- unsupported-claim rate;
- human correction/rejection rate;
- usefulness score;
- p95 end-to-end latency;
- cost per useful answer.

LLM judge is advisory until calibrated.
