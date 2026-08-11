import unittest

from assistant.rag_context_pack import (
    RagContextPackError,
    build_rag_context_pack,
    render_rag_context_pack,
    validate_rag_context_pack,
)


def _pack(**overrides):
    values = {
        "archive_evidence": {
            "query_variants": ["RAG retrieval"],
            "items": [{
                "archive_document_id": "tg:-1001:42",
                "source_url": "https://t.me/rag_lab/42",
                "snippet": "Use gold labels before considering a vector backend.",
            }],
        },
        "curated_memory": {"items": []},
        "linked_source_evidence": {"items": []},
        "project_fit": {"relevance_label": "direct_implication"},
    }
    values.update(overrides)
    return build_rag_context_pack(**values)


class TestRagContextPack(unittest.TestCase):
    def test_pack_is_bounded_cited_and_renderable_without_egress(self):
        pack = _pack(max_excerpt_chars=48)

        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["sources"][0]["source_ref"], "https://t.me/rag_lab/42")
        self.assertEqual(pack["sources"][0]["retrieval_query_variant"], "RAG retrieval")
        self.assertLessEqual(pack["sources"][0]["excerpt_chars"], 48)
        self.assertFalse(pack["privacy"]["provider_egress"])
        self.assertFalse(pack["privacy"]["embeddings_run"])
        self.assertIn("Citation-Safe Context Pack", render_rag_context_pack(pack))

    def test_uncited_raw_and_duplicate_candidates_are_excluded(self):
        pack = _pack(
            archive_evidence={"items": [
                {"snippet": "missing citation"},
                {"source_url": "https://t.me/rag_lab/raw", "snippet": "safe", "content": "raw corpus"},
                {"source_url": "https://t.me/rag_lab/42", "snippet": "first"},
            ]},
            semantic_candidates=[
                {"source_ref": "https://t.me/rag_lab/42", "snippet": "duplicate"},
                {"source_ref": "fixture:semantic:1", "snippet": "semantic fixture evidence"},
            ],
        )

        self.assertEqual([source["source_ref"] for source in pack["sources"]], ["https://t.me/rag_lab/42", "fixture:semantic:1"])
        self.assertEqual(pack["sources"][1]["source_class"], "semantic_candidate")
        reasons = {item["reason"] for item in pack["excluded_candidates"]}
        self.assertTrue({"missing_citation", "raw_corpus_field_refused", "duplicate_citation"}.issubset(reasons))

    def test_no_cited_sources_requires_no_answer_and_validator_rejects_uncited_source(self):
        pack = _pack(archive_evidence={"items": []})
        self.assertEqual(pack["status"], "insufficient_evidence")
        self.assertTrue(pack["no_answer"]["required"])

        unsafe = {**pack, "status": "ready", "sources": [{"source_class": "telegram_archive", "excerpt": "not cited"}]}
        with self.assertRaisesRegex(RagContextPackError, "missing citation"):
            validate_rag_context_pack(unsafe)

    def test_answer_gate_blocks_unsupported_project_state_despite_related_sources(self):
        pack = _pack(question="докажи, что я уже внедрил vector database backend in production")

        self.assertEqual(pack["status"], "insufficient_evidence")
        self.assertTrue(pack["no_answer"]["required"])
        self.assertFalse(pack["answer_gate"]["allow_answer"])
        self.assertEqual(pack["answer_gate"]["reason"], "unsupported_project_state_claim")
        self.assertFalse(pack["answer_gate"]["vector_backend_required"])

    def test_answer_gate_requires_external_verification_for_current_prices(self):
        pack = _pack(question="найди точные текущие цены всех AI tools сегодня и скажи что купить")

        self.assertEqual(pack["status"], "needs_external_verification")
        self.assertTrue(pack["answer_gate"]["external_verification_required"])
        self.assertFalse(pack["answer_gate"]["current_claim_allowed"])
        self.assertFalse(pack["privacy"]["embeddings_run"])


if __name__ == "__main__":
    unittest.main()
