# PRM Mature Product Contract

Status: proposed. The product is one private Telegram conversation, not a second agent platform or report engine.

## Product path and answer

`text/voice -> OperatorContext -> one workflow -> broad local retrieval -> lens soft rerank -> approved project context -> evidence classes -> optional bounded verification -> grounded synthesis -> validator -> Telegram renderer -> interaction receipt -> confirmed proposal.` Telegram discovery evidence and primary-source evidence remain distinct.

`professional_answer.v1` contains `interaction_id`, `primary_workflow`, `professional_lens`, `project_context`, `answer_status` (`supported`, `partial`, `insufficient_evidence`, `verification_required`), `short_answer`, `key_findings`, `why_for_operator`, `project_implication`, `recommended_action`, `do_not_do`, `uncertainty`, `freshness`, `evidence_classes`, `citations`, `external_verification`, `saved_memory_options`, and `telemetry_ref`.

Russian presentation is: «Короткий вывод», «Что найдено», «Почему это важно тебе», project connection only when relevant, «Что сделать», «Чего пока не делать», «Где доказательства слабые», «Источники». At most one action appears. No IDs, local paths, debug/model/cost text, or uncited factual claims appear. Validators check identity, citation-to-claim mapping, safety gates, language and project-action prerequisites; human review checks usefulness and mobile readability.

## Personalization, projects and durable loop

Lenses are explicit per question, inferred for one turn, or proposed as durable defaults only after confirmation. Candidates are `ai_systems_engineer` and `portfolio_builder`; optional lenses are career, enterprise adoption, product strategy, writer/editor and learning. Vocabulary must be bilingual, phrase/domain based and evaluated; lenses soft-rerank but never hard-filter recall.

Only approved `priority`/`active` projects are default-selectable; named `watch`/`reference` projects are explicit-only. V2 fields include status, priority, goal, blocker, next proof, capabilities, signal preferences, review/owner/source metadata and aliases. Project actions require direct cited evidence, approved project context, goal alignment, bounded step and acceptance criterion.

Proposals are durable, chat-bound, expiry-bound and idempotent: identity, interaction, hashed chat/message, type/title/summary/sources/project/payload, status, token hash, timestamps, persisted reference and idempotency key. Draft, preview/edit, confirm, cancel and expiry are distinct; confirmation is the only durable write. The private append-only interaction ledger records metadata and unknown operator labels. Raw questions require a separate approved policy. Confirmed notes, topics, links, decisions, actions, experiments, feedback and verified source cards are queryable without overriding fresh evidence.

## Freshness, verification and operations

Archive refresh, reaction sync, vector maintenance and selective enrichment are separate failure domains. Owner `/refresh` reports each independently. A reaction is a weak temporary post-level signal; emoji is audit metadata and repeated interest only proposes a preference. Live primary-source fetch is bounded and opt-in: approved host/source relation, HTTPS/SSRF/DNS/redirect/content/size/timeout/cache controls, no third-party execution. Strong-model synthesis gets only cited context, strict JSON and approved budgets; deterministic fallback remains. `/status` is friendly; debug CLI carries technical data. No automatic chat memory, raw corpus egress/logging, or value/release claim is allowed.
