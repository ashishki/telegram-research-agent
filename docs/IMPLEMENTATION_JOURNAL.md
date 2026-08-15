# Implementation Journal

## 2026-08-15 — PRM-QA evaluation-led RAG and operator-experience implementation

Baseline repository SHA: `516fc7206f99b58e6d276585c3dba6d87a39392f`.
Baseline Playbook SHA: `965612aa463fca1a35a55104633d0e09da33d615`.

Implemented PRM-QA queue slices covering private automated dataset generation,
layered eval/ablation, intent-specific retrieval policy, selected retrieval ADR,
evidence-quality contract, claim ledger, claim-level deterministic grounding
metrics, project ambiguity clarification, named-project decision memo,
job-specific Telegram rendering, usefulness feedback buttons, gitignored private
interaction/failed-case traces, and a gated primary-source verification fetcher.

Generated private dataset: 160 cases under
`data/evals/private/prm_qa/cases.v1.jsonl` (gitignored). Public manifest:
`evals/prm_qa/prm_qa_dataset_manifest.v1.json`.

Eval evidence:

- all cases: `evals/prm_qa/prm_qa_eval_report.v1.json`, status `pass`;
  routing accuracy 1.0000; selected R1 Recall@10 1.0000, MRR 0.9845, p95
  94.0055 ms; claim supported rate 0.9894; current-fact violations 0.
- holdout: `evals/prm_qa/prm_qa_holdout_report.v1.json`, status `pass`;
  34 cases; routing accuracy 1.0000; selected R1 Recall@10 1.0000, MRR 1.0000,
  p95 78.7893 ms; claim supported rate 0.9900; current-fact violations 0.

Decision: selected FTS plus bounded query rewrite with hash-vector fallback only
on FTS miss. Dense retrieval was not adopted; no local dense runtime and no
measured holdout gain.

Focused verification runs:

```text
PYTHONPATH=src python3 -m pytest tests/test_retrieval_policy.py tests/test_evidence_quality.py tests/test_claim_ledger.py tests/test_prm_qa_dataset_eval.py tests/test_prm_qa_usage_recap.py tests/test_primary_source_verification.py tests/test_pi_facade_archive_vector.py tests/test_archive_vector.py tests/test_project_context.py tests/test_pi_tools.py::TestPITools::test_project_context_tool_combines_descriptor_archive_and_curated_knowledge tests/test_prm_post_answer_actions.py tests/test_prm19_dogfood_receipts.py tests/test_handlers.py -q
118 passed in 37.26s
```

```text
python3 tools/test_tiers.py focused-prm
247 passed in 51.93s
```

```text
python3 tools/prm_mat_eval.py --check safety
prm_mat_eval: ok
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
```

CI follow-up: remote run `31899242121` exposed an environment-dependent local
path redaction regression in `memory ask`. The renderer now strips
repo-anchored absolute paths from any checkout root and falls back to basename
for other absolute local files. Follow-up verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py -q
4 passed in 1.75s
```

```text
python3 tools/test_tiers.py focused-prm
247 passed in 45.26s
```

No full pytest suite was run. No production database contents, provider call,
live Telegram job, live fetch, external embedding, hosted vector service,
dogfood start, release claim, or compatibility cleanup was performed.

## 2026-08-15 — PRM-QA API dense retrieval follow-up

The operator explicitly approved API use for assistant retrieval and embeddings
after the local-only PRM-QA pass. A repo-local `.env` was copied from
`/srv/openclaw-you/.env` and remains gitignored; secret values were not printed
or committed.

Implemented a separate API embedding sidecar:

- code: `src/db/archive_api_vector.py`
- CLI: `memory api-vector-index`, `memory api-vector-search`
- eval adapter: `R4_api_dense_candidate`
- provider/model: OpenAI `text-embedding-3-large`
- vector dimensions: 3072
- sidecar: gitignored local path data/vector/archive_api_vector.sqlite
- sidecar permissions: 0600
- sidecar size: 130.8 MB
- indexed chunks: 3,706 from 3,590 archive rows
- provider calls: 29
- input tokens: 1,356,089
- canonical DB mutated: false

API dense eval evidence:

- all cases: `evals/prm_qa/prm_qa_api_dense_report.v1.json`, status `pass`;
  R1 Recall@10 1.0000, MRR 0.9845, nDCG@10 0.9885, p95 92.9449 ms;
  R4 API dense hybrid Recall@10 1.0000, MRR 0.7917, nDCG@10 0.8451,
  p95 572.6861 ms.
- holdout: `evals/prm_qa/prm_qa_api_dense_holdout_report.v1.json`, status
  `pass`; R1 Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000, p95 86.0825 ms;
  R4 API dense hybrid Recall@10 1.0000, MRR 0.7240, nDCG@10 0.7957,
  p95 618.3259 ms.

The public API dense reports now also include `retrieval_by_job_type`, with
aggregate-only task-class metrics and no private query/source/snippet leakage.

Decision: API dense retrieval is implemented and measurable, but not adopted as
the default runtime policy because it did not improve holdout ranking and added
latency/provider cost. It remains an eval/runtime adapter for future query
shaping, chunking, fusion, or reranker work.

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_archive_api_vector.py tests/test_prm_qa_dataset_eval.py -q
4 passed in 6.25s
```

No full pytest suite was run. No production database contents, hosted vector
service, live web research, live Telegram job, production migration, dogfood
start, release claim, or compatibility cleanup was performed.

## 2026-08-15 — PRM-QA-16 API-first Telegram synthesis and job-type eval reporting

Implemented a bounded quality slice after operator approval for API-backed
assistant behavior:

- Telegram research/brief rendering now tries approved bounded API LLM synthesis
  before deterministic job-specific templates when the answer is source-backed
  and not a current-fact or ambiguous-project boundary.
- Current-fact refusal, verification-required DTO rendering, and named-project
  decision memo contracts still bypass the generic API synthesis path.
- The LLM synthesis prompt now receives the selected job type and asks for the
  matching Telegram answer contract where supported by bounded evidence.
- `tools/prm_qa_eval.py` now reports `retrieval_by_job_type` for every variant,
  preserving the public privacy boundary.

Evidence:

- `evals/prm_qa/prm_qa_api_dense_report.v1.json`, status `pass`, 160 cases.
- `evals/prm_qa/prm_qa_api_dense_holdout_report.v1.json`, status `pass`, 34
  holdout cases.
- Holdout R1 remained selected: Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000,
  context precision@5 0.2471, p95 86.0825 ms.
- Holdout R4 API dense hybrid remained non-default: Recall@10 1.0000, MRR
  0.7240, nDCG@10 0.7957, context precision@5 0.2471, p95 618.3259 ms.

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_prm_qa_dataset_eval.py -q
85 passed in 12.80s
```

```text
python3 tools/test_tiers.py focused-prm
249 passed in 29.56s
```

```text
python3 tools/prm_mat_eval.py --check safety
prm_mat_eval: ok
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
```

```text
PYTHONPATH=src python3 scripts/public_scorecard_demo.py --check
verified sha256:7b8e3203ade62c17a624888d3532b7ab6e7d639d141d6a0a78487dac18694b83 docs/evidence/public_demo_scorecard.json
```

```text
git diff --check
pass, no output
```

No full pytest suite was run. No production database contents, live Telegram job,
live web research, hosted vector service, dogfood start, release claim, or
compatibility cleanup was performed.

## 2026-08-13 — PRM-MAT documentation-only completion audit

Recorded target/Playbook baselines, component maturity, CI observation, target contract, migration/acceptance/validation plans and a 21-task proposed queue. No runtime/product code, production data, systemd state, environment value, provider call, live Telegram job, live fetch or vector rebuild was performed.

Status: active
Last updated: 2026-07-26

## 2026-07-26 - Playbook Retrofit Planning

- Repository inspected at commit ad8689fa25b89f77122c4cec7c7a6b9da3f500cf.
- AI Workflow Playbook inspected at commit 5583eca96c4d2d480b5574ed78bea63e0b07ebf0.
- Current W29 outputs were audited from the local immutable weekly run under
  data/output/weekly_intelligence_runs/tra-weekly-2026-W29-20260720T050229508302Z-978f44004e97/.
- Preferred files under /mnt/data were not available in this environment.
- Safe initializer dry-run showed duplicate architecture authority risk because
  the current Playbook would create docs/ARCHITECTURE.md while the repository
  already had docs/architecture.md.
- Direct initializer execution was not used against the repository. Current
  Playbook tools, schemas, templates, and .playbook contracts were reconciled
  manually.
- No product/runtime code was implemented.
- No production database contents were modified.
- No live Telegram ingestion, report generation, Radar run, LLM backfill,
  embeddings, or external web research job was run.
- Added jsonschema>=4.18.0 to requirements.txt and installed jsonschema 4.26.0
  in this environment because the current Playbook validator requires
  Draft202012Validator and the environment previously had jsonschema 3.2.0.
- Playbook validation passed with errors=0 warnings=0.
- Project verifier passed the Playbook contract and failed the configured pytest
  check with one current-date ops validation fixture failure:
  tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist.

## Next Journal Entry

The next implementation session should append PRM-1 evidence here after corpus
inventory and data readiness checks complete.
