# Generation Evaluation Plan

Status: draft; PRM-4 no-answer vertical slice recorded; PRM-10 grounded answer contract recorded; PRM-14 project-context answer evidence recorded
Last updated: 2026-07-28

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

## PRM-UX-2 Telegram Answer Contract

Deterministic Telegram validators check that Russian research responses include
`Короткий вывод`, `Что найдено`, `Почему это важно тебе`, `Что сделать`,
`Где доказательства слабые`, and `Источники`. They also reject local paths,
raw database identifiers, technical receipts, model/cost/token/tool/debug
fields, and internal retrieval labels. Current or high-stakes questions must
lead with the external-verification boundary and must not present archive
context as current truth.

Human review checks whether the conclusion answers the actual decision,
professional relevance is meaningful, the one next action is useful, and each
source supports the claim it follows. These checks remain human judgement, not
release evidence inferred from deterministic tests.

## PRM-UX-8 Professional Workflow Projections

The AI-systems workflow projects bounded local evidence into a failure taxonomy,
cited cases, an approved-project implication, and at most one proposed eval
case. A direct project action requires direct project evidence and no
current-fact verification boundary.

The writer/editor workflow returns an input brief only: a thesis, up to three
source-backed cases, counterargument, practical conclusion, source links, and
an explicit list of claims requiring external verification. It always marks
the result as not ready for a final post and does not publish or write content.
Deterministic tests cover field presence, source-only cases, and the current
fact boundary; human review remains responsible for editorial quality.

The enterprise AI adoption workflow treats archive material as discovery
evidence only. It exposes a pain pattern, owner signal, project implication,
validation step, and a do-not-build boundary. A project action is possible only
for a direct project implication; otherwise the result is watch/reference
guidance without a recommendation to build.

The learning workflow returns a simple explanation, analogy, cited local
evidence, one proposed experiment, success criterion, and reflection question.
It reports learning state as `unknown` unless explicit evidence exists, and its
experiment is confirmation-gated with no write performed by the projection.

The career/portfolio workflow labels absent local portfolio evidence as
`unknown` rather than fabricating proof. Any current job-market implication is
held behind primary-source verification, and no portfolio action is proposed
until direct project evidence is available.

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
- If a generation step returns archive claims when the trace is
  `insufficient_evidence` and no grounding evidence exists, the assistant
  replaces the model text with deterministic insufficient-evidence fallback.
- Telemetry privacy flags assert that raw post text, raw tool payloads, and
  provider payloads were not logged. Bounded snippet provider context is
  recorded separately from broad raw corpus egress. PI chat suppresses
  `llm_usage` database writes during read-only planning/generation.

Verification command:

```bash
python3 -m pytest tests/test_pi_chat.py tests/test_pi_tools.py tests/test_archive_search.py tests/test_archive_documents.py -q
```

Result:

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
39 passed, 6 subtests passed in 14.25s
python3 tools/test_tiers.py focused-prm
65 passed, 6 subtests passed in 12.74s
python3 tools/test_tiers.py fast-contract
118 passed, 6 subtests passed in 58.27s
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

## PRM-14 Project Context Answer Evidence

Implementation:

- Project-application chat routes call `analyze_project_context`
  deterministically.
- Final project-context answers are rendered from
  `project_context_decision_support.v1`; they do not need an LLM generation
  call.
- Answers name the active project, relevance label, descriptor fields used,
  source refs, suggestion/watch guidance, unknowns, and the mutation boundary.
- Weak keyword-only, learning-only, and no-match labels do not produce action
  recommendations.
- The grounded answer contract still records archive support and source links
  from the DTO evidence.

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_project_context.py tests/test_pi_tools.py tests/test_pi_chat.py -q
47 passed, 6 subtests passed in 5.59s
python3 tools/test_tiers.py focused-prm
78 passed, 6 subtests passed in 11.38s
python3 tools/test_tiers.py fast-contract
131 passed, 6 subtests passed in 33.79s
```
