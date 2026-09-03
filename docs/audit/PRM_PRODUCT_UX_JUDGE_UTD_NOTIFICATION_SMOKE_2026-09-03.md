# PRM Product UX Judge

Generated: `2026-09-03T11:13:17Z`
Status: `pass`
Reason: LLM judge executed without warnings

This is an advisory product/UX evaluation. It is not dogfood evidence, not a release claim, and not a substitute for operator labels.

## Scope

- Provider: `codex-exec`
- Model: `gpt-5.6-terra`
- Reasoning effort: `medium`
- Case selection: `{"end_index_exclusive": 174, "selected_count": 2, "start_index": 172, "total_built_count": 548}`
- Corpus metrics: `{"dialogue_turns": 980, "dialogues": 130, "one_turn_cases": 288}`

## Metrics

| Metric | Value |
| --- | --- |
| `case_count` | 2 |
| `turn_count` | 2 |
| `deterministic_failure_case_count` | 0 |
| `deterministic_failure_counts` | {} |
| `judged_count` | 2 |
| `provider_failure_count` | 0 |
| `verdict_counts` | {"pass": 2} |
| `quality_floor` | 4.0 |
| `score_means` | {"actionability_score": 5.0, "clarity_score": 4.0, "dialogue_coherence_score": 5.0, "directness_score": 4.5, "low_cognitive_load_score": 4.0, "naturalness_score": 3.0, "notification_relevance_score": 4.5, "one_bot_coherence_score": 5.0, "personalization_score": 4.0, "safety_boundary_score": 5.0} |
| `score_floor_failure_count` | 0 |
| `human_review_count` | 0 |
| `would_user_know_next_step_rate` | 2/2 (100.00%) |
| `lost_context_count` | 0 |
| `notification_noise_count` | 0 |
| `one_bot_fragmentation_count` | 0 |
| `privacy_boundary_violation_count` | 0 |
| `unsafe_or_overconfident_count` | 0 |
| `elapsed_ms` | 25439.669 |

## Deterministic Failures

No deterministic product-check failures in the selected shard.

## LLM Verdicts

| Case | Verdict | Mean score | Human review | Summary | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| `judge:one:utd:notification:program:01` | `pass` | 4.4 | False | Релевантное, проверяемое и ненавязчивое уведомление с понятным следующим шагом. | Сделать заголовок и блоки чуть естественнее по-русски, сохранив ссылку и время проверки. |
| `judge:one:utd:notification:program:02` | `pass` | 4.4 | False | Полезное, проверяемое и ненавязчивое уведомление с понятным следующим шагом. | Сделать заголовок полностью по-русски или добавить короткий русский перевод. |

## Privacy Boundary

- Raw private Telegram corpus was not sent to the judge.
- Telegram messages were not sent.
- Production DB writes were not requested.
- Detailed judge datasets/results are gitignored.
