# ADR-006: Intent-first archive answers

- Status: proposed for operator smoke
- Date: 2026-08-16
- Owners: repository operator and PRM maintainers
- Scope: active PRM Telegram/CLI request-to-answer path

## Context

A simple archive question such as:

`Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?`

could be transformed into a project-decision response containing a watch recommendation, project goal, blocker, acceptance criterion, backlog language, and a large action keyboard. The failure did not require hallucination: the response could be formally grounded in one archive source while still failing the user's actual job.

The root causes were architectural:

- top-level routing exposed only coarse modes such as `research`;
- archive lookup, applicability, project mapping, and decision support shared one payload;
- project context could be inferred without a named project;
- project-context retrieval could search for evidence after a weak keyword match;
- the renderer selected a decision template from the presence of a project packet rather than from explicit intent;
- retrieval variants were consumed sequentially without an explicit directness contract;
- Telegram actions depended on project-name presence rather than intent and relevance;
- evaluations rewarded route presence, citations, and grounding but did not reliably penalize intent substitution.

A repository retrofit introduced a typed application boundary, but intentionally did not change retrieval policy or prove operator usefulness. Therefore the boundary alone did not correct the behavior.

## Decision

Adopt an intent-first, source-first answer boundary.

### 1. Semantic intent is explicit

Every active PRM route records a `primary_intent` and `response_contract_id`. Coarse transport mode remains for compatibility, but it is not the product intent.

### 2. Archive scope has priority over a lone temporal word

`сейчас` or `now` does not activate current-fact verification when the question is explicitly scoped to the retained archive. Current verification requires an external/current claim or an explicit verification request.

### 3. Project context is opt-in for the primary answer

Archive lookup, synthesis, and archive-to-action do not expose the project resolver. A project must be named or explicitly selected before project mapping or decision support can dominate the answer.

### 4. Retrieval is phrase-first and relevance-labelled

Mixed-language canonical phrases are preserved. Bounded aliases are searched before broad concept expansions. Candidates are classified as `direct`, `partial`, `adjacent`, or `unrelated` and reranked before evidence selection.

### 5. The renderer follows the response contract

`archive_lookup.v2` and `archive_research.v2` render a source-first archive response. A project decision template is rendered only for `decision_support.v2`. The existence of a project packet is no longer sufficient to select the decision template.

### 6. Synthesis cannot change the user job

Optional LLM synthesis receives only the active answer contract. Archive synthesis does not receive a project-decision packet and is rejected if it introduces project blockers, backlog language, acceptance criteria, or other decision-template sections.

### 7. Telegram actions are progressive

Feedback and retrieval refinement are available first. Durable notes, links, actions, and experiments are shown only when their prerequisites are met. Feedback is immediate; persistent memory actions remain confirmation-gated.

### 8. Evaluation includes semantic and UX failure modes

Regression evidence must cover intent accuracy, implicit project-context rate, external-verification false positives, direct-answer position, direct/adjacent separation, answer length, irrelevant-template rate, and public-report privacy.

## Consequences

### Positive

- Archive questions answer the archive question first.
- A single archive document is sufficient to report archive presence.
- Adjacent materials can remain useful without being misrepresented.
- Project policy cannot silently dominate generic research.
- Mixed Russian-English terminology receives an explicit retrieval path.
- The existing SQLite FTS and local optional vector sidecar remain usable; no hosted vector database or external embedding model is required.
- The design remains deterministic when provider egress is disabled.
- Private failure traces become more diagnostic without publishing private text.

### Costs and risks

- Implicit project suggestions become less aggressive.
- Existing generated/silver eval data may need semantic-intent labels before it can be treated as a strong routing benchmark.
- Directness rules require bounded maintenance and human calibration.
- The temporary compatibility path means both old and new response shapes coexist until operator smoke is complete.
- Optional LLM synthesis can still reduce UX quality; deterministic fallback remains authoritative.

## Alternatives considered

### Prompt-only repair

Rejected. The wrong project and response contract were selected before synthesis. A prompt cannot reliably repair an incorrect route and evidence packet.

### Add a new vector database or embedding provider

Rejected for this change. The primary defect was intent and ranking policy, not absence of a storage engine. It would also expand privacy, cost, deployment, and reindexing scope without proving benefit.

### Require two sources for all answers

Rejected. One source is enough to state that a material exists in the archive. Corroboration is claim-dependent, not a universal archive-lookup gate.

### Remove project context entirely

Rejected. Project mapping and decision support are valuable when explicitly requested. They are separated, not deleted.

### Keep automatic project selection but lower its confidence

Rejected. Even a low-confidence implicit project can contaminate retrieval and rendering. A follow-up suggestion is safer than silent primary-answer substitution.

## Rollout

1. Merge only after focused PRM, retrofit-boundary, MAT safety, Playbook, and public-evidence checks pass.
2. Keep provider egress disabled for deterministic regression replay.
3. Run the synthetic reference replay.
4. Run the owner smoke set against a production-equivalent local database with no Telegram sends and no writes.
5. Deploy the candidate commit to the manual-test runtime only after deployment parity is recorded.
6. Restart only the active PRM assistant unit after explicit operator approval.
7. Do not start PRM-19 dogfood or make release/value claims from this change.

## Rollback

Rollback is code-only:

- revert the candidate PR or deploy the prior known-good commit;
- restart the active PRM assistant unit only if a deployment occurred;
- do not roll back the canonical Telegram database;
- do not delete private feedback receipts or local vector sidecars as part of code rollback;
- retain the old deterministic presentation fallback until operator smoke accepts the new contract.

## Acceptance evidence

The minimum acceptance set includes:

- exact reference query routes to `archive_to_action`;
- no implicit project context;
- no false external-verification requirement from `сейчас` alone;
- direct evaluation fixture ranks above Agent Operations;
- adjacent-only fixture reports zero direct matches;
- archive answer begins with a direct answer and excludes decision-template sections;
- Telegram actions depend on intent and relevance;
- public eval/replay summaries contain no raw query, raw Telegram body, source URL, or private candidate ID;
- operator smoke is recorded separately from automated regression evidence.
