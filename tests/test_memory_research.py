import unittest

from assistant.memory_research import (
    MemoryResearchBudget,
    answer_memory_research,
    render_memory_research_answer,
)


class _FakeFacade:
    def __init__(self, project_label="direct_implication"):
        self.project_label = project_label
        self.calls = []

    def search_telegram_archive(self, query, filters=None, limit=5):
        self.calls.append("search_telegram_archive")
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


class TestMemoryResearch(unittest.TestCase):
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
        self.assertIn("Archive signal", result["direct_answer"])
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
        self.assertIn("Direct Answer", rendered)
        self.assertIn("Telegram Archive Evidence", rendered)
        self.assertIn("Linked Source Evidence", rendered)
        self.assertIn("Approach Comparison", rendered)
        self.assertIn("Project Fit", rendered)
        self.assertIn("Citation-Safe Context Pack", rendered)
        self.assertIn("Deeper Reading", rendered)
        self.assertIn("Draft Proposals", rendered)
        self.assertIn("Privacy: mode=local-research; model_calls=0; estimated_cost_usd=0", rendered)

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
        self.assertIn("Status: refused", render_memory_research_answer(result))

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
