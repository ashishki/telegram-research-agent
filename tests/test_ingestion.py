import sqlite3
import unittest

from ingestion.bootstrap_ingest import _build_message_url, _insert_message


class TestBootstrapIngestion(unittest.TestCase):
    def test_insert_message_populates_message_url(self):
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                """
                CREATE TABLE raw_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    posted_at TEXT NOT NULL,
                    text TEXT,
                    media_type TEXT,
                    media_caption TEXT,
                    forward_from TEXT,
                    view_count INTEGER,
                    message_url TEXT,
                    raw_json TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    image_description TEXT
                )
                """
            )
            row = {
                "channel_username": "@testchan",
                "channel_id": 1,
                "message_id": 123,
                "posted_at": "2026-03-31T00:00:00Z",
                "text": "message",
                "media_type": "none",
                "media_caption": None,
                "forward_from": None,
                "view_count": 0,
                "message_url": _build_message_url("@testchan", 123),
                "raw_json": "{}",
                "ingested_at": "2026-03-31T00:00:01Z",
                "image_description": None,
            }

            _insert_message(connection.cursor(), row)
            inserted_url = connection.execute(
                "SELECT message_url FROM raw_posts WHERE channel_username = ? AND message_id = ?",
                ("@testchan", 123),
            ).fetchone()[0]

        self.assertEqual(inserted_url, "https://t.me/testchan/123")


if __name__ == "__main__":
    unittest.main()
