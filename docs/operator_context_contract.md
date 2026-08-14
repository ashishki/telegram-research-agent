# Canonical OperatorContext Contract

Status: proposed for PRM-MAT-1. Design only; this neither adds a runtime schema nor authorizes storage.

Every normal Telegram text or voice request creates exactly one `OperatorContext` with `schema_version: operator_context.v1` and an opaque `interaction_id`. Required fields are `interaction_id`, `chat_id_hash`, `session_id`, `input_kind`, `language`, `normalized_query`, `primary_intent`, `primary_workflow`, `secondary_lens`, `explicit_lens`, `inferred_lens`, `project_name`, `project_selection_source`, `date_from`, `date_to`, `freshness_requirement`, `evidence_requirements`, `external_verification_requirement`, `answer_mode`, `clarification_required`, `route_confidence`, `durable_write_allowed`, `privacy_mode`, and `created_at`.

`original_query_local_ref` is allowed only if an approved private retention policy permits it. It is never placed in commits, exports, provider inputs, receipts, or Telegram callback data. Route, retrieval, synthesis, renderer, receipt and proposal all preserve `interaction_id`; later stages may refuse/clarify but cannot independently change workflow, project, date window or evidence requirements.

## Routing and sessions

Select exactly one primary workflow: `archive_research`, `ai_systems_project_application`, `career_portfolio_gap`, `enterprise_ai_adoption`, `product_strategy`, `writer_editor_brief`, `learning_experiment`, `reaction_recall`, `saved_knowledge_recall`, `current_fact_verification`, `generic_chat`, or `insufficient_evidence`. There is at most one secondary lens. Slash commands override style, never freshness/current/high-stakes safety. Low confidence asks one compact clarification.

Keep six context summaries for 30 minutes per hashed chat in memory. A summary has identity, workflow, topic fingerprint and bounded query derivative; it is not durable memory. Restart clears it and prompts a friendly continuation. Topic change, slash override or expiry starts a session. Saving is always explicit confirmation.

## Validation

Deterministic checks reject missing identity, multiple workflows, project actions without approved context/direct evidence, and current claims without current evidence. Human review follows one fixture trace from input through final buttons.
