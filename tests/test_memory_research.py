import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from assistant.memory_research import (
    MemoryResearchBudget,
    _archive_query_variants,
    answer_memory_research,
    render_memory_research_answer,
    render_memory_research_brief,
)
from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal
from config.settings import Settings
from db.migrate import run_migrations


class _FakeFacade:
    def __init__(self, project_label="direct_implication"):
        self.project_label = project_label
        self.calls = []
        self.archive_filters = []

    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_filters.append(dict(filters or {}))
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:1001",
                    "posted_at": "2026-08-03T10:00:00Z",
                    "channel_username": "@eval_lab",
                    "source_url": "https://t.me/eval_lab/1001",
                    "snippet": (
                        "Eval gates for coding agents should compare cited claims "
                        "against gold labels. Read https://example.com/blog/rag-evals"
                    ),
                }
            ][:limit],
        }

    def search_intelligence_items(self, query, filters=None, limit=5):
        self.calls.append("search_intelligence_items")
        return {
            "status": "ok",
            "query": query,
            "items": [
                {
                    "id": "claim-1",
                    "item_type": "claim_card",
                    "title": "Grounded eval gates",
                    "summary": "Eval gates help prevent unsupported release claims.",
                    "source_refs": ["https://t.me/eval_lab/1002"],
                    "atom_ids": [501],
                }
            ][:limit],
        }

    def analyze_project_context(self, query, project_name=None, week_label=None, limit=5):
        self.calls.append("analyze_project_context")
        return {
            "schema_version": "project_context_decision_support.v1",
            "status": "ok",
            "query": query,
            "project_name": project_name or "Eval-Ground-Truth-Lab",
            "relevance_label": self.project_label,
            "descriptor_fields_used": ["keywords", "focus"],
            "source_refs": ["https://t.me/eval_lab/1001"],
            "unknowns": [] if self.project_label == "direct_implication" else ["direct project implication"],
            "decision_support": {
                "automatic_mvp_build_approval": False,
                "code_mutation_exposed": False,
                "project_mutation_exposed": False,
                "write_performed": False,
                "requires_human_confirmation_for_saves": True,
            },
        }


class _SelectiveArchiveFacade(_FakeFacade):
    def __init__(self):
        super().__init__()
        self.archive_queries = []

    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_queries.append(query)
        self.archive_filters.append(dict(filters or {}))
        if query != "RAG retrieval":
            return {
                "status": "insufficient_evidence",
                "query": query,
                "retrieval_mode": "sqlite_fts_archive",
                "items": [],
            }
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:2001",
                    "posted_at": "2026-08-03T11:00:00Z",
                    "channel_username": "@rag_lab",
                    "source_url": "https://t.me/rag_lab/2001",
                    "snippet": "RAG retrieval needs gold-label evals before vector backend adoption.",
                }
            ][:limit],
        }


class _RelatedOnlyProjectStateFacade(_FakeFacade):
    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_filters.append(dict(filters or {}))
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:3001",
                    "posted_at": "2026-08-03T12:00:00Z",
                    "channel_username": "@rag_lab",
                    "source_url": "https://t.me/rag_lab/3001",
                    "snippet": "pgvector retrieval and vector backend adoption were discussed as a gated future option.",
                }
            ][:limit],
        }


class _AITransformationFacade(_FakeFacade):
    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_filters.append(dict(filters or {}))
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:4001",
                    "posted_at": "2026-07-06T09:00:00Z",
                    "channel_username": "@redmad",
                    "source_url": "https://t.me/redmad/4001",
                    "snippet": (
                        "Только 1% компаний считает своё внедрение ИИ по-настоящему успешным; "
                        "пилоты есть, но реальный эффект и финансовая выгода требуют процесса."
                    ),
                }
            ][:limit],
        }


class _StaleModelsFacade(_FakeFacade):
    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_filters.append(dict(filters or {}))
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:5001",
                    "posted_at": "2026-05-22T09:00:00Z",
                    "channel_username": "@model_old",
                    "source_url": "https://t.me/model_old/5001",
                    "snippet": "Old model launch context that must not answer a last-two-weeks question.",
                }
            ][:limit],
        }


class _MixedModelsFacade(_FakeFacade):
    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
        self.archive_filters.append(dict(filters or {}))
        return {
            "status": "ok",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:5101",
                    "posted_at": "2026-07-20T09:00:00Z",
                    "channel_username": "@model_old",
                    "source_url": "https://t.me/model_old/5101",
                    "snippet": "Older model item outside the requested window.",
                },
                {
                    "archive_document_id": "tg:-1001:5102",
                    "posted_at": "2026-08-05T09:00:00Z",
                    "channel_username": "@model_recent",
                    "source_url": "https://t.me/model_recent/5102",
                    "snippet": "Fresh LLM model release inside the requested window.",
                },
            ][:limit],
        }


class TestMemoryResearch(unittest.TestCase):
    def test_confirmed_saved_memory_is_secondary_to_archive_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "memory.db")
            previous = os.environ.get("AGENT_DB_PATH")
            os.environ["AGENT_DB_PATH"] = db_path
            try:
                run_migrations()
                draft = build_memory_proposal("knowledge_note", {"title": "Eval gates", "body": "Saved note", "source_refs": ["https://t.me/saved/1"]})
                confirm_memory_proposal(db_path, {"proposal": draft["proposal"], "confirmation_token": draft["confirmation"]["token"]})
                facade = _FakeFacade()
                facade._settings = Settings(db_path=db_path, llm_api_key="", model_provider="", telegram_session_path="")
                result = answer_memory_research("Eval gates", facade=facade, budget=MemoryResearchBudget(max_archive_sources=1, max_linked_sources=1))
            finally:
                if previous is None:
                    os.environ.pop("AGENT_DB_PATH", None)
                else:
                    os.environ["AGENT_DB_PATH"] = previous
        self.assertEqual(result["archive_evidence"]["items"][0]["source_url"], "https://t.me/eval_lab/1001")
        self.assertTrue(result["curated_memory"]["items"])
        self.assertTrue(result["curated_memory"].get("items")[0].get("citation", "").startswith("memory:"))
    def test_memory_research_includes_matching_workflow_section_in_shared_dto(self):
        result = answer_memory_research(
            "How should eval gates affect Eval-Ground-Truth-Lab?",
            facade=_FakeFacade(),
            project_name="Eval-Ground-Truth-Lab",
            operator_context={
                "interaction_id": "fixture-interaction",
                "primary_workflow": "archive_research",
            },
        )

        answer = result["professional_answer"]
        self.assertEqual(answer["interaction_id"], "fixture-interaction")
        self.assertEqual(answer["primary_workflow"], "archive_research")
        self.assertEqual(answer["workflow_section"], result["professional_workflows"]["ai_systems"])

    def test_memory_research_builds_project_decision_from_approved_claim_ledger(self):
        result = answer_memory_research(
            "Что из материалов про eval gates применимо к Eval-Ground-Truth-Lab?",
            facade=_FakeFacade(),
            project_name="Eval-Ground-Truth-Lab",
            operator_context={
                "interaction_id": "decision-interaction",
                "primary_workflow": "archive_research",
            },
        )

        decision = result["project_decision"]

        self.assertEqual(decision["schema_version"], "prm_project_decision_synthesis.v1")
        self.assertEqual(decision["project_name"], "Eval-Ground-Truth-Lab")
        self.assertTrue(result["candidate_claim_ledger"]["claims"])
        self.assertTrue(result["claim_ledger"]["claims"])
        self.assertTrue(decision["approved_claim_refs"])
        self.assertTrue(decision["current_blocker"])
        self.assertTrue(decision["next_proof"])
        self.assertTrue(decision["grounded_recommendation"])
        self.assertTrue(decision["acceptance_criterion"])
        self.assertFalse(decision["write_performed"])

    def test_memory_research_maps_career_section_to_archive_workflow(self):
        result = answer_memory_research(
            "What portfolio evidence is useful for an AI career?",
            facade=_FakeFacade(),
            project_name="Eval-Ground-Truth-Lab",
            operator_context={"interaction_id": "career-interaction", "primary_workflow": "archive_research"},
        )

        self.assertEqual(
            result["professional_answer"]["workflow_section"],
            result["professional_workflows"]["career_portfolio"],
        )

    def test_memory_research_produces_polished_fixture_answer_without_writes_or_egress(self):
        result = answer_memory_research(
            "How should eval gates affect Eval-Ground-Truth-Lab?",
            facade=_FakeFacade(),
            project_name="Eval-Ground-Truth-Lab",
            linked_source_fixtures={
                "https://example.com/blog/rag-evals": {
                    "title": "RAG Eval Gates",
                    "text": "A grounded answer should cite retrieved claims, compare evidence, and flag unsupported claims.",
                    "fetched_at": "2026-08-03T10:05:00Z",
                }
            },
        )

        self.assertEqual(result["schema_version"], "memory_research_answer.v1")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Found", result["direct_answer"])
        self.assertIn("First useful signal", result["direct_answer"])
        self.assertNotIn("Archive signal", result["direct_answer"])
        self.assertNotIn("Project routing", result["direct_answer"])
        self.assertEqual(result["archive_evidence"]["retrieval_mode"], "sqlite_fts_archive_query_planner")
        self.assertTrue(result["archive_evidence"]["query_variants"])
        self.assertEqual(result["linked_source_evidence"]["extracted_count"], 1)
        self.assertEqual(result["linked_source_evidence"]["items"][0]["normalized_title"], "RAG Eval Gates")
        self.assertTrue(result["approach_comparison"])
        self.assertEqual(result["project_fit"]["relevance_label"], "direct_implication")
        self.assertIn("Draft one bounded project action", result["next_steps"]["apply"][0])
        self.assertIn("https://example.com/blog/rag-evals", [item.get("url") for item in result["deeper_reading_path"]])
        self.assertIn("live external freshness", result["unknowns"])
        self.assertEqual(result["receipt"]["tool_calls_used"], 4)
        self.assertEqual(result["privacy"]["model_calls"], 0)
        self.assertFalse(result["privacy"]["bounded_telegram_snippet_provider_egress"])
        self.assertFalse(result["privacy"]["external_skill_used"])
        self.assertFalse(result["privacy"]["durable_writes"])
        self.assertEqual(result["context_pack"]["status"], "ready")
        self.assertFalse(result["context_pack"]["privacy"]["provider_egress"])

        proposals = result["draft_proposals"]
        self.assertGreaterEqual(len(proposals), 2)
        self.assertTrue(all(proposal["status"] == "needs_confirmation" for proposal in proposals))
        self.assertTrue(all(not proposal["persisted"] for proposal in proposals))
        self.assertTrue(all(not proposal["write_performed"] for proposal in proposals))
        self.assertTrue(all(proposal["confirmation"]["token"].startswith("confirm-") for proposal in proposals))

        rendered = render_memory_research_answer(result)
        self.assertIn("PRM Research", rendered)
        self.assertIn("Short answer", rendered)
        self.assertIn("Sources", rendered)
        self.assertIn("Next steps", rendered)
        self.assertIn("Details: add --debug", rendered)
        self.assertNotIn("Citation-Safe Context Pack", rendered)
        self.assertNotIn("Approach Comparison", rendered)
        self.assertIn("Privacy: mode=local-research; model_calls=0; estimated_cost_usd=0", rendered)

        debug_rendered = render_memory_research_answer(result, debug=True)
        self.assertIn("Direct Answer", debug_rendered)
        self.assertIn("Telegram Archive Evidence", debug_rendered)
        self.assertIn("Linked Source Evidence", debug_rendered)
        self.assertIn("Approach Comparison", debug_rendered)
        self.assertIn("Project Fit", debug_rendered)
        self.assertIn("Citation-Safe Context Pack", debug_rendered)
        self.assertIn("Deeper Reading", debug_rendered)
        self.assertIn("Draft Proposals", debug_rendered)

    def test_memory_research_rewrites_natural_rag_question_to_short_archive_query(self):
        facade = _SelectiveArchiveFacade()

        result = answer_memory_research(
            "ок, а что с рагом, он точно нужен или SQLite FTS пока достаточно?",
            facade=facade,
            project_name="telegram-research-agent",
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("RAG retrieval", facade.archive_queries)
        self.assertIn("RAG retrieval", result["archive_evidence"]["query_variants"])
        self.assertEqual(result["archive_evidence"]["items"][0]["matched_query_variant"], "RAG retrieval")
        first_call = result["receipt"]["tool_calls"][0]
        self.assertEqual(first_call["name"], "search_telegram_archive")
        self.assertIn("query_variants", first_call["arguments"])
        self.assertNotIn("project_name", first_call["arguments"]["filters"])
        self.assertEqual(result["receipt"]["tool_calls_used"], 4)

    def test_memory_research_hybrid_budget_passes_vector_mode_without_path_leak(self):
        facade = _FakeFacade()

        result = answer_memory_research(
            "How should eval gates affect Eval-Ground-Truth-Lab?",
            facade=facade,
            project_name="Eval-Ground-Truth-Lab",
            budget=MemoryResearchBudget(
                allow_vector_retrieval=True,
                vector_index_path="/tmp/private-vector-sidecar.sqlite",
            ),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["archive_evidence"]["retrieval_mode"], "hybrid_local_vector_archive_query_planner")
        self.assertEqual(facade.archive_filters[0]["retrieval_mode"], "hybrid")
        self.assertEqual(facade.archive_filters[0]["vector_index_path"], "/tmp/private-vector-sidecar.sqlite")
        self.assertNotIn("/tmp/private-vector-sidecar.sqlite", json.dumps(result, ensure_ascii=False))
        first_call_filters = result["receipt"]["tool_calls"][0]["arguments"]["filters"]
        self.assertNotIn("vector_index_path", first_call_filters)
        self.assertTrue(first_call_filters["vector_index_path_configured"])
        self.assertNotIn("vector_index_path", result["receipt"]["budget"])
        self.assertTrue(result["receipt"]["budget"]["vector_index_path_configured"])
        self.assertTrue(result["receipt"]["privacy"]["vector_backend_used"])
        self.assertEqual(result["receipt"]["privacy"]["local_embedding_backend"], "local_hashing_text_vector.v1")
        self.assertFalse(result["receipt"]["privacy"]["external_embedding_provider_egress"])
        rendered = render_memory_research_answer(result)
        self.assertIn("vector_backend_used=true", rendered)

    def test_memory_research_adds_ai_transformation_editorial_query_variants(self):
        variants = _archive_query_variants(
            "собери опорные тезисы для поста: AI трансформация компаний, где эффект есть, где нет",
            project_name=None,
            max_variants=4,
        )

        self.assertIn("внедрение ИИ компании успешным", variants)
        self.assertIn("AI transformation companies ROI productivity", variants)
        self.assertNotEqual(variants[0], "AI собери опорные тезисы поста")

    def test_memory_research_adds_ai_model_query_variants(self):
        variants = _archive_query_variants(
            "Что было интересного по моделям за последние две недели?",
            project_name=None,
            max_variants=4,
        )

        self.assertIn("AI models LLM", variants)
        self.assertIn("LLM GPT Claude Gemini", variants)
        self.assertIn("модели ИИ LLM", variants)
        self.assertNotIn("последние", " ".join(variants).casefold())

    def test_memory_research_normalizes_russian_harness_inflections(self):
        variants = _archive_query_variants(
            "Что было полезного для моих проектов в контексте харнесса?",
            project_name=None,
            max_variants=4,
        )

        self.assertIn("harness", variants)

    def test_memory_research_keeps_agent_evals_in_archive_query_variants(self):
        variants = _archive_query_variants(
            "Что в моём архиве было про agent evals и что мне с этим делать?",
            project_name=None,
            max_variants=4,
        )

        self.assertIn("agent evals", variants)
        self.assertNotIn("моём архиве", " ".join(variants).casefold())

    def test_memory_research_uses_semantic_archive_query_but_keeps_original_question(self):
        facade = _SelectiveArchiveFacade()

        result = answer_memory_research(
            "Что полезно для моих проектов?",
            archive_query="RAG retrieval",
            facade=facade,
        )

        self.assertEqual(result["question"], "Что полезно для моих проектов?")
        self.assertEqual(facade.archive_queries[0], "RAG retrieval")

    def test_memory_research_enforces_last_two_weeks_and_rejects_stale_hits(self):
        facade = _StaleModelsFacade()

        result = answer_memory_research(
            "Что было интересного по моделям за последние две недели?",
            facade=facade,
            now=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["time_window"]["date_from"], "2026-07-28T00:00:00Z")
        self.assertEqual(result["time_window"]["date_to"], "2026-08-12T00:00:00Z")
        self.assertTrue(all(item.get("date_from") == "2026-07-28T00:00:00Z" for item in facade.archive_filters))
        self.assertTrue(all(item.get("date_to") == "2026-08-12T00:00:00Z" for item in facade.archive_filters))
        self.assertEqual(result["archive_evidence"]["items"], [])
        self.assertTrue(
            any(attempt.get("rejected_by_time_window") for attempt in result["archive_evidence"]["attempted_queries"])
        )

        rendered = render_memory_research_answer(result)

        self.assertIn("В локальном архиве за 2026-07-28–2026-08-11 не нашёл релевантных постов", rendered)
        self.assertNotIn("Old model launch", rendered)
        self.assertNotIn("2026-05-22", rendered)

    def test_memory_research_keeps_recent_hits_inside_requested_window(self):
        result = answer_memory_research(
            "Что было интересного по моделям за последние две недели?",
            facade=_MixedModelsFacade(),
            now=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
        )

        items = result["archive_evidence"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_url"], "https://t.me/model_recent/5102")
        rendered = render_memory_research_answer(result)
        self.assertIn("Fresh LLM model release", rendered)
        self.assertIn("2026-08-05", rendered)
        self.assertNotIn("Older model item", rendered)
        self.assertNotIn("2026-07-20", rendered)

    def test_memory_research_archive_scoped_recent_posts_are_not_current_fact_refusal(self):
        result = answer_memory_research(
            "что из постов за последние месяцы говорит что AI трансформация не дала прироста и почему?",
            facade=_AITransformationFacade(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["answer_gate"]["external_verification_required"])
        rendered = render_memory_research_answer(result)
        self.assertIn("разрыв между AI-пилотами", rendered)
        self.assertNotIn("Сначала ограничение", rendered)

    def test_memory_research_retrospective_project_question_uses_archive_evidence(self):
        result = answer_memory_research(
            "Что было полезного для моих проектов в последние пару недель?",
            archive_query="eval gates",
            facade=_FakeFacade(),
            now=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["answer_gate"]["allow_answer"])
        self.assertFalse(result["answer_gate"]["external_verification_required"])

    def test_memory_research_archive_context_does_not_override_current_price_boundary(self):
        result = answer_memory_research(
            "какая текущая цена акций Nvidia сегодня и что об этом говорит мой архив?",
            facade=_FakeFacade(),
        )

        self.assertEqual(result["status"], "needs_external_verification")
        self.assertTrue(result["answer_gate"]["external_verification_required"])
        self.assertFalse(result["answer_gate"]["current_claim_allowed"])
        self.assertIn("Сначала ограничение", render_memory_research_answer(result))

    def test_memory_research_dialog_context_keeps_topic_summary_for_short_followups(self):
        original = "что у меня было про AI transformation компаний, где есть эффект, а где нет?"
        result = answer_memory_research(original, facade=_AITransformationFacade())
        result = {
            **result,
            "question": "а почему?",
            "dialog_context": {
                "used": True,
                "previous_question": original,
                "effective_question": f"{original}. Уточнение: а почему?",
            },
        }

        rendered = render_memory_research_answer(result)

        self.assertIn("Контекст диалога", rendered)
        self.assertIn("разрыв между AI-пилотами", rendered)

    def test_memory_research_brief_renders_source_backed_editor_points(self):
        result = answer_memory_research(
            "собери опорные тезисы для поста: AI трансформация компаний, где эффект есть, где нет",
            facade=_AITransformationFacade(),
        )

        rendered = render_memory_research_brief(result)

        self.assertIn("PRM редакторский бриф", rendered)
        self.assertIn("Опорные тезисы", rendered)
        self.assertIn("Углы для поста", rendered)
        self.assertIn("пилоты vs результат", rendered)
        self.assertIn("Privacy: mode=local-research; model_calls=0", rendered)

    def test_memory_research_brief_without_sources_offers_plain_next_steps(self):
        result = answer_memory_research("собери тезисы для поста про AI adoption", facade=_FakeFacade())

        rendered = render_memory_research_brief(result)

        self.assertIn("Как продолжим", rendered)
        self.assertIn("Сформулируй тему шире", rendered)
        self.assertIn("Пришли ссылку или материал", rendered)

    def test_memory_research_compact_render_localizes_russian_and_prioritizes_freshness(self):
        result = answer_memory_research(
            "какая текущая цена акций Nvidia сегодня?",
            facade=_FakeFacade(),
        )

        rendered = render_memory_research_answer(result)

        self.assertIn("Вопрос: какая текущая цена акций Nvidia сегодня?", rendered)
        self.assertIn("Короткий ответ", rendered)
        self.assertIn("Сначала ограничение", rendered)
        self.assertIn("Источники", rendered)
        self.assertEqual(result["draft_proposals"], [])
        self.assertNotIn("Черновики", rendered)
        self.assertNotIn("Direct Answer", rendered)
        self.assertNotIn("Citation-Safe Context Pack", rendered)

    def test_memory_research_compact_render_routes_repo_questions_to_repo_context_first(self):
        result = answer_memory_research(
            "что мне делать дальше по telegram research agent?",
            facade=_FakeFacade(project_label="learning_relevance"),
        )

        self.assertEqual(result["repo_project_context"]["status"], "matched")
        self.assertIn("docs/tasks.md", result["repo_project_context"]["source_refs"])

        rendered = render_memory_research_answer(result)

        self.assertIn("Контекст проекта", rendered)
        self.assertIn("документы репозитория", rendered)
        self.assertIn("docs/tasks.md", rendered)

    def test_memory_research_blocks_unsupported_project_state_claim_despite_related_hits(self):
        result = answer_memory_research(
            "докажи, что я уже внедрил vector database backend in production",
            facade=_RelatedOnlyProjectStateFacade(),
            project_name="telegram-research-agent",
        )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["answer_gate"]["reason"], "unsupported_project_state_claim")
        self.assertFalse(result["answer_gate"]["allow_answer"])
        self.assertIn("не цитируемое доказательство", result["direct_answer"])
        self.assertEqual(result["draft_proposals"], [])
        self.assertEqual(result["receipt"]["draft_proposal_count"], 0)
        self.assertFalse(result["privacy"]["provider_egress"])

    def test_memory_research_requires_external_verification_for_current_prices(self):
        result = answer_memory_research(
            "найди точные текущие цены всех AI tools сегодня и скажи что купить",
            facade=_FakeFacade(),
        )

        self.assertEqual(result["status"], "needs_external_verification")
        self.assertTrue(result["answer_gate"]["external_verification_required"])
        self.assertFalse(result["answer_gate"]["current_claim_allowed"])
        self.assertEqual(result["draft_proposals"], [])
        self.assertIn("Нужна внешняя проверка", result["direct_answer"])
        self.assertFalse(result["privacy"]["provider_egress"])

    def test_memory_research_refuses_open_browsing_before_tool_calls(self):
        facade = _FakeFacade()

        result = answer_memory_research(
            "посмотри в интернете свежие цены и сравни",
            facade=facade,
        )

        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["receipt"]["refusal_reason"], "open_ended_browsing_refused")
        self.assertEqual(result["receipt"]["tool_calls_used"], 0)
        self.assertEqual(facade.calls, [])
        self.assertIn("Статус: отказано", render_memory_research_answer(result))

    def test_memory_research_refuses_provider_budget_switches(self):
        result = answer_memory_research(
            "Summarize eval gates",
            facade=_FakeFacade(),
            budget=MemoryResearchBudget(max_model_calls=1, max_cost_usd=0.01, allow_provider_egress=True),
        )

        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["receipt"]["refusal_reason"], "provider_egress_refused")
        self.assertEqual(result["privacy"]["model_calls"], 0)
        self.assertFalse(result["privacy"]["provider_egress"])

    def test_memory_research_refuses_unbounded_or_disabled_source_limits(self):
        result = answer_memory_research(
            "Summarize eval gates",
            facade=_FakeFacade(),
            budget=MemoryResearchBudget(max_linked_sources=0),
        )

        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["receipt"]["refusal_reason"], "linked_source_budget_refused")
        self.assertEqual(result["receipt"]["tool_calls_used"], 0)

    def test_memory_research_reports_project_labels_without_mutation(self):
        for label in ("direct_implication", "weak_watch", "learning_relevance", "no_match"):
            with self.subTest(label=label):
                result = answer_memory_research(
                    "Does this apply to a project?",
                    facade=_FakeFacade(project_label=label),
                    linked_source_fixtures={
                        "https://example.com/blog/rag-evals": {
                            "title": "RAG Eval Gates",
                            "text": "Citation checks are useful.",
                        }
                    },
                )
                self.assertEqual(result["project_fit"]["relevance_label"], label)
                self.assertFalse(result["project_fit"]["decision_support"]["write_performed"])
                self.assertFalse(result["project_fit"]["decision_support"]["project_mutation_exposed"])

    def test_memory_research_reports_ambiguous_project_from_fixture_candidates(self):
        result = answer_memory_research(
            "Does this apply to my eval project or research memory project?",
            facade=_FakeFacade(project_label="no_match"),
            project_context_fixtures=[
                {
                    "project_name": "Eval-Ground-Truth-Lab",
                    "relevance_label": "weak_watch",
                    "source_refs": ["https://t.me/eval_lab/1001"],
                },
                {
                    "project_name": "Telegram Research Memory",
                    "relevance_label": "learning_relevance",
                    "source_refs": ["https://t.me/memory/1002"],
                },
            ],
        )

        self.assertEqual(result["project_fit"]["relevance_label"], "ambiguous_project")
        self.assertEqual(len(result["project_fit"]["candidate_projects"]), 2)
        self.assertIn("target project selection", result["unknowns"])
        self.assertFalse(result["project_fit"]["decision_support"]["project_mutation_exposed"])


if __name__ == "__main__":
    unittest.main()
