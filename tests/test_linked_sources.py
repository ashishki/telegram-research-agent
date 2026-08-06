import unittest

from assistant.linked_sources import (
    FakeLinkedSourceFetcher,
    LinkedSourceResolver,
    classify_source_url,
    extract_linked_source_candidates,
    resolve_linked_sources,
)


class _ApprovalGatedFetcher:
    requires_live_http = True
    requires_external_skill = True
    requires_provider_summarization = True

    def __init__(self):
        self.calls = 0

    def fetch(self, source_url):
        self.calls += 1
        raise AssertionError(f"unapproved fetch should not run for {source_url}")


class TestLinkedSources(unittest.TestCase):
    def test_url_extraction_and_classification_cover_prm22_source_types(self):
        posts = [
            {
                "archive_document_id": "tg:-1001:101",
                "text": (
                    "Article https://example.com/blog/rag-evals?utm_source=tg and "
                    "docs https://docs.python.org/3/library/urllib.parse.html."
                ),
            },
            {
                "archive_document_id": "tg:-1001:102",
                "text": (
                    "GitHub https://github.com/openai/openai-python/pull/123, "
                    "paper https://arxiv.org/abs/2501.00001, video https://youtu.be/abc123."
                ),
            },
            {
                "archive_document_id": "tg:-1001:103",
                "text": (
                    "Product https://linear.app/pricing and unknown https://example.invalid/resource. "
                    "Ignore Telegram permalink https://t.me/source/103."
                ),
            },
        ]

        candidates = extract_linked_source_candidates(posts, limit=10)
        by_type = {candidate.source_type: candidate.normalized_url for candidate in candidates}

        self.assertEqual(len(candidates), 7)
        self.assertEqual(classify_source_url("https://example.com/blog/rag-evals"), "article")
        self.assertIn("article", by_type)
        self.assertIn("docs", by_type)
        self.assertIn("github", by_type)
        self.assertIn("paper", by_type)
        self.assertIn("video", by_type)
        self.assertIn("product", by_type)
        self.assertIn("unknown", by_type)
        self.assertNotIn("https://t.me/source/103", [candidate.normalized_url for candidate in candidates])
        self.assertEqual(by_type["article"], "https://example.com/blog/rag-evals")

    def test_fake_fetcher_populates_sanitized_cache_records(self):
        posts = [
            {
                "archive_document_id": "tg:-1001:201",
                "text": "Read https://example.com/blog/rag-evals and https://docs.example.com/guide.",
            }
        ]
        fetcher = FakeLinkedSourceFetcher(
            {
                "https://example.com/blog/rag-evals": {
                    "title": "  RAG   Eval Gates  ",
                    "text": " Eval gates compare cited claims against gold labels. " * 20,
                    "fetched_at": "2026-08-03T10:00:00Z",
                    "raw_payload": {"raw_html": "<html>not cached</html>", "token": "secret"},
                },
                "https://docs.example.com/guide": {
                    "status": "failed",
                    "failure_reason": "token=super-secret <html>provider payload should be redacted</html>",
                    "fetched_at": "2026-08-03T10:01:00Z",
                },
            }
        )

        result = resolve_linked_sources(posts, fetcher=fetcher, fetched_at="2026-08-03T10:02:00Z")
        records = {record["normalized_url"]: record for record in result["cache_records"]}
        extracted = records["https://example.com/blog/rag-evals"]
        failed = records["https://docs.example.com/guide"]

        self.assertEqual(result["status"], "partial")
        self.assertEqual(extracted["extraction_status"], "extracted")
        self.assertEqual(extracted["fetched_at"], "2026-08-03T10:00:00Z")
        self.assertEqual(extracted["source_url"], "https://example.com/blog/rag-evals")
        self.assertEqual(extracted["normalized_title"], "RAG Eval Gates")
        self.assertEqual(len(extracted["content_hash"]), 64)
        self.assertLessEqual(len(extracted["text_excerpt"]), 500)
        self.assertEqual(failed["extraction_status"], "failed")
        self.assertIn("token=<redacted>", failed["redacted_failure_reason"])
        self.assertNotIn("super-secret", failed["redacted_failure_reason"])
        self.assertNotIn("<html>provider payload", failed["redacted_failure_reason"])

        forbidden_cache_keys = {"raw_html", "provider_payload", "raw_provider_payload", "telegram_text"}
        for record in result["cache_records"]:
            self.assertTrue(forbidden_cache_keys.isdisjoint(record))

        receipt = result["receipt"]
        self.assertEqual(receipt["schema_version"], "linked_source_research_receipt.v1")
        self.assertFalse(receipt["privacy"]["provider_payload_logged"])
        self.assertFalse(receipt["privacy"]["external_skill_used"])
        self.assertFalse(receipt["privacy"]["raw_telegram_corpus_egress"])
        self.assertEqual(receipt["privacy"]["model_calls"], 0)
        self.assertEqual(receipt["privacy"]["estimated_cost_usd"], 0.0)

    def test_unapproved_live_external_provider_fetcher_is_refused_before_fetch(self):
        posts = [
            {
                "archive_document_id": "tg:-1001:301",
                "text": "Current source https://example.com/blog/current-agent-market.",
            }
        ]
        fetcher = _ApprovalGatedFetcher()
        resolver = LinkedSourceResolver(fetcher=fetcher)

        result = resolver.resolve(posts, fetched_at="2026-08-03T11:00:00Z")

        self.assertEqual(fetcher.calls, 0)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["receipt"]["mode"], "approval_gated")
        self.assertEqual(result["cache_records"][0]["extraction_status"], "refused")
        reason = result["cache_records"][0]["redacted_failure_reason"]
        self.assertIn("live_http_fetch", reason)
        self.assertIn("external_skill", reason)
        self.assertIn("provider_summarization", reason)
        self.assertFalse(result["receipt"]["privacy"]["live_http_fetch_used"])
        self.assertFalse(result["receipt"]["privacy"]["external_skill_used"])
        self.assertFalse(result["receipt"]["privacy"]["provider_summarization_used"])


if __name__ == "__main__":
    unittest.main()
