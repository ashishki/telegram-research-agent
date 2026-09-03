# PRM Product UX Judge

Generated: `2026-09-03T11:01:11Z`
Status: `needs_human_review`
Reason: LLM judge scores fell below floor

This is an advisory product/UX evaluation. It is not dogfood evidence, not a release claim, and not a substitute for operator labels.

## Scope

- Provider: `codex-exec`
- Model: `gpt-5.6-terra`
- Reasoning effort: `medium`
- Case selection: `{"end_index_exclusive": 2, "selected_count": 2, "start_index": 0, "total_built_count": 260}`
- Corpus metrics: `{"dialogue_turns": 980, "dialogues": 130, "one_turn_cases": 288}`

## Metrics

| Metric | Value |
| --- | --- |
| `case_count` | 2 |
| `turn_count` | 8 |
| `deterministic_failure_case_count` | 0 |
| `deterministic_failure_counts` | {} |
| `judged_count` | 2 |
| `provider_failure_count` | 0 |
| `verdict_counts` | {"warn": 2} |
| `quality_floor` | 4.0 |
| `score_means` | {"actionability_score": 2.5, "clarity_score": 3.0, "dialogue_coherence_score": 2.0, "directness_score": 2.5, "low_cognitive_load_score": 2.0, "naturalness_score": 3.0, "notification_relevance_score": 5.0, "one_bot_coherence_score": 2.5, "personalization_score": 2.5, "safety_boundary_score": 5.0} |
| `score_floor_failure_count` | 2 |
| `human_review_count` | 0 |
| `would_user_know_next_step_rate` | 1/2 (50.00%) |
| `lost_context_count` | 2 |
| `notification_noise_count` | 0 |
| `one_bot_fragmentation_count` | 1 |
| `privacy_boundary_violation_count` | 0 |
| `unsafe_or_overconfident_count` | 0 |
| `elapsed_ms` | 31104.695 |

## Deterministic Failures

No deterministic product-check failures in the selected shard.

## LLM Verdicts

| Case | Verdict | Mean score | Human review | Summary | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| `judge:dialogue:prm:agent_evals:01:turns_001_004` | `warn` | 3.2 | False | Границы источников соблюдены, но ответ на бриф теряет контекст предыдущего проектного вопроса и перегружен. | В брифе сохраняй активный проект telegram-research-agent, убери служебную многословность и явно поясняй, что «Сохранить» требует отдельного подтверждения. |
| `judge:dialogue:prm:agent_evals:01:turns_005_008` | `warn` | 2.8 | False | Границы безопасности соблюдены, но бот не выполняет ясные follow-up-запросы и теряет контекст внешней проверки. | Показывайте запрошенный черновик и подтверждение прямо в ответе, а для внешней свежести кратко предлагайте проверку без подмены её архивом. |

## Privacy Boundary

- Raw private Telegram corpus was not sent to the judge.
- Telegram messages were not sent.
- Production DB writes were not requested.
- Detailed judge datasets/results are gitignored.
