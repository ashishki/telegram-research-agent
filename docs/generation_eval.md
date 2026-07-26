# Generation Evaluation Plan

Status: draft

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
