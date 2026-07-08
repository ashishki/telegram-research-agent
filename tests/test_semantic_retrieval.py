import unittest
from unittest.mock import patch

from assistant.semantic_retrieval import retrieval_decision_note, search_curated_semantic_items
from output.intelligence_retrieval_items import IntelligenceRetrievalItem


class TestCuratedSemanticRetrieval(unittest.TestCase):
    def test_fts_expansion_finds_curated_mvp_radar_item(self):
        items = [
            IntelligenceRetrievalItem(
                id="mvp_dossier:2026-W28:agent-eval-gate-scanner",
                item_type="mvp_dossier",
                week_label="2026-W28",
                title="Agent Eval Gate Scanner",
                text="MVP opportunity validation has missing market demand evidence.",
                source_refs=["/tmp/mvp-weekly-2026-W28.json"],
                atom_ids=[101],
                status="revisit_with_evidence_gap",
            )
        ]

        results = search_curated_semantic_items(items, "радар рынка", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["item_type"], "mvp_dossier")
        self.assertIn("curated", results[0]["retrieval_mode"])
        self.assertEqual(results[0]["source_refs"], ["/tmp/mvp-weekly-2026-W28.json"])
        self.assertEqual(results[0]["atom_ids"], [101])

    def test_filters_apply_before_fts_indexing(self):
        items = [
            IntelligenceRetrievalItem(
                id="claim_card:2026-W27:market-demand",
                item_type="claim_card",
                week_label="2026-W27",
                title="Market demand evidence",
                text="Market demand validation is strong.",
            ),
            IntelligenceRetrievalItem(
                id="claim_card:2026-W28:agent-evals",
                item_type="claim_card",
                week_label="2026-W28",
                title="Agent evals",
                text="Agent eval gates matter for release discipline.",
            ),
        ]

        results = search_curated_semantic_items(
            items,
            "market demand",
            filters={"week_label": "2026-W28"},
            limit=5,
        )

        self.assertEqual(results, [])

    def test_raw_telegram_item_types_are_not_indexed(self):
        items = [
            IntelligenceRetrievalItem(
                id="raw_post:1",
                item_type="raw_telegram_post",
                week_label="2026-W28",
                title="Raw post",
                text="Secret raw Telegram firehose text about market demand.",
            ),
            IntelligenceRetrievalItem(
                id="knowledge_atom:1",
                item_type="knowledge_atom",
                week_label="2026-W28",
                title="Curated atom",
                text="Curated market demand evidence.",
            ),
        ]

        results = search_curated_semantic_items(items, "market demand", limit=5)

        self.assertEqual([item["id"] for item in results], ["knowledge_atom:1"])

    def test_decision_note_defers_vector_and_raw_rag(self):
        decision = retrieval_decision_note()

        self.assertEqual(decision["mode"], "curated_deterministic_plus_sqlite_fts")
        self.assertEqual(decision["raw_telegram_status"], "disabled")
        self.assertIn("deferred", decision["vector_status"])

    def test_deterministic_fallback_when_fts_is_unavailable(self):
        items = [
            IntelligenceRetrievalItem(
                id="claim_card:2026-W28:eval-gates",
                item_type="claim_card",
                week_label="2026-W28",
                title="Eval gates",
                text="Eval gates are release infrastructure.",
                source_refs=["https://t.me/source/1"],
                atom_ids=[101],
            )
        ]

        with patch("assistant.semantic_retrieval._fts_search", return_value=[]):
            results = search_curated_semantic_items(items, "eval gates", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["retrieval_mode"], "curated_deterministic_fallback")
        self.assertEqual(results[0]["source_refs"], ["https://t.me/source/1"])
        self.assertEqual(results[0]["atom_ids"], [101])


if __name__ == "__main__":
    unittest.main()
