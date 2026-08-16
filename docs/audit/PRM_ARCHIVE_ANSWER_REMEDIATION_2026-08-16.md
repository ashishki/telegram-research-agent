# PRM Archive Answer Remediation Review — 2026-08-16

Status: implementation candidate; not deployed; not dogfood evidence
Branch: `agent/intent-first-archive-answers`
Base: `master` at `1edd65618806d663886cc960817ca2690a05f742`

## Trigger

The operator asked:

`Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?`

The observed Telegram answer began with a project decision to keep a signal on watch, used adjacent Agent Operations material, did not disclose whether direct `agent evals` materials existed, introduced project/backlog policy, and attached a large action keyboard.

## Root cause confirmed in code

The review identified a compound product-architecture failure rather than a single prompt defect:

1. coarse `research` routing did not encode the operator's actual job;
2. a lone `сейчас` could influence top-level current routing;
3. query extraction could retain wrapper words and lose the most useful phrase;
4. project context was invoked even when no project was named;
5. project descriptor selection allowed weak keyword matching;
6. project context performed a second project-expanded retrieval;
7. project-decision synthesis was created as part of every research response;
8. presentation selected a decision template from packet presence;
9. retrieval did not expose direct/partial/adjacent relevance before presentation;
10. the keyboard was driven by project-name presence rather than intent and evidence quality;
11. automated evaluations checked grounding and route shape more strongly than question answering and mobile usefulness.

The current global answer gate was not the primary cause. It already permits a single archive source to support the statement that a material exists in the archive. The second-source/backlog language came from the incorrectly activated project-decision path.

## Implemented changes

### Semantic routing

The route now records:

- `primary_intent`;
- `response_contract_id`;
- archive scope;
- project-context requirement;
- external-verification requirement;
- decision-request flag;
- reason codes.

The reference query deterministically resolves to:

```text
mode: research
primary_intent: archive_to_action
response_contract_id: archive_research.v2
retrieval_query: agent evals
project_context_required: false
external_verification_required: false
decision_requested: false
```

### Project isolation

Archive intents use `ArchiveScopedResearchFacade`, which exposes archive and curated reads but deliberately does not expose `analyze_project_context`. The application also clears project fit and project decision from archive contracts.

This prevents an unrequested keyword such as `eval` from silently selecting a project and changing the retrieval/response job.

### Retrieval relevance

A deterministic classifier labels each candidate:

- `direct`;
- `partial`;
- `adjacent`;
- `unrelated`.

For the reference topic:

- explicit agent-evaluation phrases are direct;
- combined agent and evaluation concepts are direct;
- evaluation without explicit agent scope is partial;
- Agent Operations/access/audit material without evaluation practice is adjacent.

Candidate ranking uses relevance class and directness before lexical/vector tie-breakers. Existing SQLite FTS and the optional local vector sidecar remain unchanged as storage boundaries.

### Source-first archive contract

`prm_archive_answer.v2` contains:

- direct conclusion;
- direct/partial/adjacent counts;
- separated findings;
- applicability inferences;
- limitations;
- sources;
- bounded query refinements;
- explicit project and external-verification boundaries.

When no direct source exists, the response must say so. An adjacent source cannot be promoted into a direct finding.

### Presentation and synthesis

Archive rendering is selected by `response_contract_id`, not by the incidental presence of a project packet. Decision-only sections are excluded from archive answers.

Optional LLM synthesis receives the archive contract and selected source summaries. It does not receive the project-decision packet. The synthesis result is rejected if it introduces project blocker, backlog, acceptance-criterion, or other decision-template language.

### Telegram UX

Archive actions are progressive:

- `Полезно`, `Частично`, `Мимо`;
- `Показать ещё` and `Уточнить поиск` after any relevant result;
- `Сохранить заметку` after direct or partial evidence;
- project links only with explicit project context and relevant evidence.

`Следить`, stored actions, and stored experiments are no longer shown before relevance is established. Feedback is recorded immediately on the new intent path. Durable memory writes remain confirmation-gated.

### Replay, eval, and observability

Added a single-query replay tool supporting:

- a synthetic fixture; or
- a read-only local SQLite database.

It disables provider egress and synthesis, sends no Telegram messages, and performs no durable writes.

Eval V2 and live UX evaluation now record/check:

- semantic intent accuracy;
- implicit project-context rate;
- external-verification false-positive rate;
- direct/adjacent retrieval labels;
- direct-answer start;
- irrelevant project-template rate;
- mobile answer length;
- no-direct disclosure;
- public-report privacy.

Private receipts include intent, response contract, relevance counts, and hashed selected evidence IDs. Public summaries exclude raw queries, raw archive text, source URLs, candidate IDs, and chat IDs.

## Synthetic reference replay

Fixture contents are synthetic and contain no private Telegram text:

- one direct source about task success, groundedness, tool-call correctness, regression, and gold labels;
- one adjacent Agent Operations source about access and audit;
- one unrelated product-design hard negative.

Expected outcome:

- direct source rank 1;
- Agent Operations labelled adjacent;
- unrelated source excluded from the displayed evidence;
- direct count 1;
- adjacent count 1;
- no project context;
- no external verification;
- no decision-template rendering.

A second holdout with the direct source removed must report zero direct matches and show Agent Operations only as adjacent.

## Safety boundary

This branch does not:

- deploy or restart a service;
- modify the production database;
- run Telegram ingestion or reaction sync;
- export the private archive;
- enable provider egress;
- call a live model;
- build a hosted vector service;
- start PRM-19 dogfood;
- make release or product-value claims.

## Verification plan

Repository policy prohibits using the complete historical suite as the normal verification loop. The candidate must pass:

```bash
python tools/test_tiers.py focused-prm
python tools/test_tiers.py retrofit-boundaries
python tools/prm_mat_eval.py --check safety
python tools/playbook_validate.py --root . --check tasks --check references
PYTHONPATH=src python3 scripts/public_scorecard_demo.py --check
git diff --check
```

The synthetic replay must also pass:

```bash
PYTHONPATH=src python3 tools/prm_replay_query.py \
  --query 'Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?' \
  --fixture tests/fixtures/prm_agent_evals_replay.json
```

Automated pass status remains regression evidence only. Operator usefulness requires the separate owner smoke test.

## Remaining risks

- Existing private eval cases may not carry semantic intent labels and therefore cannot independently prove intent quality.
- Directness rules are deterministic heuristics and require owner calibration on real misses.
- Production deployment parity remains unverified until VPS commit, unit, environment, and restart time are recorded.
- The new follow-up buttons return safe callback receipts but deeper interactive query refinement may require a later dedicated conversation-state slice.
- No claim is made that hybrid retrieval improves this failure mode until measured against directness-labelled holdouts.

## Recommendation

Merge only after CI, independent self-review, and owner smoke acceptance. Deploy as a manual-test candidate first. Retain the previous application/presentation path as code rollback until the operator confirms that archive answers are faster, more direct, and more useful on a representative 15–20 question set.
