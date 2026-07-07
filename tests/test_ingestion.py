import asyncio
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from ingestion.bootstrap_ingest import _build_message_url, _cutoff_date_for_days, _ingest_channel, _insert_message


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

    def test_cutoff_date_uses_requested_days(self):
        before = datetime.now(timezone.utc)
        cutoff = _cutoff_date_for_days(84)
        after = datetime.now(timezone.utc)

        self.assertLessEqual((before - cutoff).days, 84)
        self.assertGreaterEqual((after - cutoff).days, 84)

    def test_cutoff_date_rejects_empty_window(self):
        with self.assertRaises(ValueError):
            _cutoff_date_for_days(0)

    def test_ingest_channel_skips_duplicate_before_photo_analysis(self):
        class FakeClient:
            def __init__(self, message):
                self.message = message

            async def get_entity(self, channel_username):
                return channel_username

            def iter_messages(self, entity, offset_date, reverse):
                async def _messages():
                    yield self.message

                return _messages()

            async def download_media(self, message, output_type):
                raise AssertionError("duplicate photo should not be downloaded")

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
                    image_description TEXT,
                    UNIQUE(channel_id, message_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO raw_posts (
                    channel_username, channel_id, message_id, posted_at, raw_json, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("@testchan", 1234, 55, "2026-07-01T00:00:00+00:00", "{}", "2026-07-01T00:00:01+00:00"),
            )
            connection.commit()
            message = SimpleNamespace(
                id=55,
                peer_id=SimpleNamespace(channel_id=1234),
                date=datetime.now(timezone.utc) - timedelta(days=1),
                message="",
                photo=True,
                video=False,
                document=False,
                fwd_from=None,
                views=10,
            )

            with patch("ingestion.bootstrap_ingest.analyze_photo") as analyze_photo, patch(
                "ingestion.bootstrap_ingest.append_source_events"
            ) as append_source_events:
                result = asyncio.run(
                    _ingest_channel(
                        FakeClient(message),
                        connection,
                        {"username": "@testchan"},
                        datetime.now(timezone.utc) - timedelta(days=84),
                    )
                )

            self.assertEqual(result, {"inserted": 0, "skipped": 1, "errors": 0})
            analyze_photo.assert_not_called()
            append_source_events.assert_called_once_with([])


if __name__ == "__main__":
    unittest.main()
