import unittest

from assistant.local_memory_ask import answer_local_memory_question, render_local_memory_answer
from assistant.project_context import build_project_context_decision_support


class _FakeFacade:
    def search_intelligence_items(self, query, filters=None, limit=10):
        return {
            "status": "ok",
            "query": query,
            "filters": filters or {},
            "items": [
                {
                    "id": "claim-1",
                    "item_type": "claim_card",
                    "title": "Eval gates",
                    "summary": "Eval gates are practical release infrastructure.",
                    "source_refs": ["https://t.me/source/1"],
                    "atom_ids": [101],
                }
            ],
            "message": "Curated intelligence items matched deterministic search.",
        }

    def search_telegram_archive(self, query, filters=None, limit=10):
        return {
            "status": "ok",
            "query": query,
            "filters": filters or {},
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:1001",
                    "posted_at": "2026-07-20T10:00:00Z",
                    "channel_username": "@source",
                    "source_url": "https://t.me/source/1001",
                    "snippet": "Teams use eval gates to catch regressions before release.",
                }
            ],
            "message": "Telegram archive posts matched SQLite FTS search.",
        }

    def analyze_project_context(self, query, project_name=None, week_label=None, limit=5):
        return build_project_context_decision_support(
            query=query,
            project_descriptor={
                "name": project_name or "Eval-Ground-Truth-Lab",
                "repo": "ashishki/Eval-Ground-Truth-Lab",
                "description": "Evaluation lab for coding-agent ground truth.",
                "focus": "gold labels, holdout sets, citation correctness",
                "keywords": ["eval", "ground truth", "gold labels", "citation correctness"],
            },
            archive_result={
                "status": "ok",
                "items": [
                    {
                        "archive_document_id": "tg:-1001:1001",
                        "posted_at": "2026-07-20T10:00:00Z",
                        "source_url": "https://t.me/source/1001",
                        "snippet": "Coding-agent evals need ground truth labels.",
                    }
                ],
            },
            curated_result={
                "status": "ok",
                "items": [
                    {
                        "id": "claim-1",
                        "item_type": "claim_card",
                        "summary": "Evidence-backed acceptance fixtures help judge calibration.",
                        "source_refs": ["https://t.me/source/1002"],
                        "atom_ids": [101],
                    }
                ],
            },
        )


class TestLocalMemoryAsk(unittest.TestCase):
    def test_local_memory_ask_returns_evidence_without_model_or_writes(self):
        result = answer_local_memory_question(
            "Какие практики есть по eval gates?",
            facade=_FakeFacade(),
            limit=3,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "local_only")
        self.assertEqual(result["privacy"]["model_calls"], 0)
        self.assertFalse(result["privacy"]["bounded_telegram_snippet_provider_egress"])
        self.assertFalse(result["privacy"]["write_performed"])
        self.assertIn("search_intelligence_items", [call["name"] for call in result["tool_calls"]])
        self.assertIn("search_telegram_archive", [call["name"] for call in result["tool_calls"]])
        self.assertIn("https://t.me/source/1001", result["evidence"]["source_refs"])
        self.assertIn("Knowledge signals", result["answer"])
        self.assertIn("Archive evidence", result["answer"])

        rendered = render_local_memory_answer(result)
        self.assertIn("PRM Memory", rendered)
        self.assertIn("no LLM, no external search, no writes", rendered)
        self.assertIn("raw_corpus_egress=False", rendered)

    def test_local_memory_ask_project_scope_uses_project_context(self):
        result = answer_local_memory_question(
            "Можно применить eval gates?",
            facade=_FakeFacade(),
            project_name="Eval-Ground-Truth-Lab",
            limit=3,
        )

        self.assertEqual([call["name"] for call in result["tool_calls"]], ["analyze_project_context"])
        self.assertIn("Project context: Eval-Ground-Truth-Lab", result["answer"])
        self.assertIn("Boundary: no MVP build approval", result["answer"])
        self.assertEqual(result["privacy"]["model_calls"], 0)

    def test_local_memory_ask_external_questions_do_not_run_external_search(self):
        result = answer_local_memory_question(
            "Какие свежие цены у этого продукта сегодня?",
            facade=_FakeFacade(),
        )

        self.assertEqual([call["name"] for call in result["tool_calls"]], ["request_external_verification"])
        self.assertIn("External verification is required", result["answer"])
        self.assertIn("No external request was run", result["answer"])
        self.assertFalse(result["privacy"]["external_skill_used"])


if __name__ == "__main__":
    unittest.main()
