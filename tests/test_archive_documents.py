import unittest

from db.archive_documents import (
    ArchiveDocumentError,
    archive_post_document_id,
    build_archive_documents,
    content_hash,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "post_id": 10,
        "raw_post_id": 20,
        "channel_username": "@source",
        "channel_id": -100123,
        "message_id": 456,
        "posted_at": "2026-07-20T10:00:00Z",
        "message_url": "https://t.me/source/456",
        "language_detected": "ru",
        "content": "Short Telegram post with enough searchable content.",
        "forward_from": "",
    }
    row.update(overrides)
    return row


class TestArchiveDocumentIdentity(unittest.TestCase):
    def test_normal_post_maps_to_single_stable_document(self):
        result = build_archive_documents([_row()])

        self.assertEqual(result.exclusions, ())
        self.assertEqual(len(result.documents), 1)
        document = result.documents[0]
        self.assertEqual(document.archive_document_id, "tg:-100123:456")
        self.assertEqual(document.post_archive_document_id, "tg:-100123:456")
        self.assertEqual(document.post_id, 10)
        self.assertEqual(document.raw_post_id, 20)
        self.assertEqual(document.channel_username, "@source")
        self.assertEqual(document.channel_id, -100123)
        self.assertEqual(document.message_id, 456)
        self.assertEqual(document.source_url, "https://t.me/source/456")
        self.assertEqual(document.language, "ru")
        self.assertEqual(
            document.content_hash,
            content_hash("Short Telegram post with enough searchable content."),
        )
        self.assertEqual(document.chunk_content_hash, document.content_hash)
        self.assertIsNone(document.chunk_index)
        self.assertEqual(document.chunk_count, 1)
        self.assertIsNone(document.duplicate_cluster_id)

    def test_archive_post_document_id_uses_channel_id_and_message_id(self):
        self.assertEqual(
            archive_post_document_id(channel_id=-100123, message_id=456),
            "tg:-100123:456",
        )

    def test_missing_required_identity_field_raises(self):
        with self.assertRaises(ArchiveDocumentError):
            build_archive_documents([_row(channel_id=None)])


class TestArchiveDocumentChunking(unittest.TestCase):
    def test_long_post_chunks_preserve_post_level_citation(self):
        content = (
            "first section has searchable context and exact citation. "
            "second section carries more context for retrieval. "
            "third section keeps the source URL attached to every chunk. "
        ) * 4

        result = build_archive_documents([_row(content=content)], chunk_max_chars=120)

        self.assertEqual(result.exclusions, ())
        self.assertGreater(len(result.documents), 1)
        chunk_count = len(result.documents)
        for index, document in enumerate(result.documents):
            self.assertEqual(document.post_archive_document_id, "tg:-100123:456")
            self.assertEqual(document.source_url, "https://t.me/source/456")
            self.assertEqual(document.content_hash, content_hash(content))
            self.assertEqual(document.chunk_index, index)
            self.assertEqual(document.chunk_count, chunk_count)
            self.assertEqual(document.archive_document_id, f"tg:-100123:456:chunk:{index:04d}")
            self.assertLessEqual(len(document.content), 120)
            self.assertLess(document.chunk_start_char, document.chunk_end_char)

    def test_blank_post_is_excluded_from_indexable_documents(self):
        result = build_archive_documents([_row(content="   ")])

        self.assertEqual(result.documents, ())
        self.assertEqual(len(result.exclusions), 1)
        exclusion = result.exclusions[0]
        self.assertEqual(exclusion.post_id, 10)
        self.assertEqual(exclusion.raw_post_id, 20)
        self.assertEqual(exclusion.archive_document_id, "tg:-100123:456")
        self.assertEqual(exclusion.reason, "empty_canonical_body")


class TestArchiveDocumentDedupe(unittest.TestCase):
    def test_exact_duplicate_posts_share_duplicate_cluster(self):
        result = build_archive_documents(
            [
                _row(post_id=1, raw_post_id=101, channel_id=-1001, message_id=11, content="Same body"),
                _row(post_id=2, raw_post_id=102, channel_id=-1002, message_id=22, content=" same   BODY "),
                _row(post_id=3, raw_post_id=103, channel_id=-1003, message_id=33, content="Different body"),
            ]
        )

        by_post_id = {document.post_id: document for document in result.documents}
        self.assertEqual(by_post_id[1].content_hash, by_post_id[2].content_hash)
        self.assertIsNotNone(by_post_id[1].duplicate_cluster_id)
        self.assertEqual(by_post_id[1].duplicate_cluster_id, by_post_id[2].duplicate_cluster_id)
        self.assertIsNone(by_post_id[3].duplicate_cluster_id)

    def test_forwarded_post_gets_repost_cluster_hash_without_source_text(self):
        result = build_archive_documents([_row(forward_from="@upstream")])

        document = result.documents[0]
        self.assertRegex(document.repost_cluster_id or "", r"^forward:[0-9a-f]{16}$")
        self.assertNotIn("@upstream", document.repost_cluster_id or "")

    def test_missing_source_url_falls_back_to_telegram_coordinates(self):
        result = build_archive_documents([_row(message_url="")])

        self.assertEqual(result.documents[0].source_url, "https://t.me/source/456")


if __name__ == "__main__":
    unittest.main()
