import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from output.ai_transformation_source_packet import (
    TelegramPost,
    build_ai_transformation_source_packet,
    fetch_telegram_preview_posts,
    parse_telegram_preview_posts,
)


class TestAiTransformationSourcePacket(unittest.TestCase):
    def test_parse_telegram_preview_posts_extracts_text_metrics_and_skips_service_messages(self):
        html = """
        <div class="tgme_widget_message text_not_supported_wrap service_message js-widget_message" data-post="ai_lab/99">
          <div class="tgme_widget_message_text js-message_text" dir="auto">pinned message</div>
          <a class="tgme_widget_message_date" href="https://t.me/ai_lab/99"><time datetime="2026-08-09T10:00:00+00:00"></time></a>
        </div>
        <div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="ai_lab/100">
          <div class="tgme_widget_message_text js-message_text" dir="auto">Microsoft внедряет AI в поддержку: productivity +20%, но найм заморожен.<br/>Причина — интеграция в процесс.</div>
          <div class="tgme_widget_message_reactions js-message_reactions"><span>❤</span>12<span>👍</span>3</div>
          <span class="tgme_widget_message_views">1.2K</span>
          <a class="tgme_widget_message_date" href="https://t.me/ai_lab/100"><time datetime="2026-08-09T11:00:00+00:00"></time></a>
        </div>
        """

        posts = parse_telegram_preview_posts(html, channel_username="@ai_lab")

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].message_id, 100)
        self.assertEqual(posts[0].views, 1200)
        self.assertEqual(posts[0].reactions, 15)
        self.assertIn("productivity +20%", posts[0].text)
        self.assertEqual(posts[0].source_url, "https://t.me/ai_lab/100")

    def test_fetch_telegram_preview_posts_paginates_until_cutoff(self):
        pages = {
            "https://t.me/s/ai_lab": """
                <div class="tgme_widget_message js-widget_message" data-post="ai_lab/200">
                  <div class="tgme_widget_message_text js-message_text">AI company transformation with revenue growth.</div>
                  <a class="tgme_widget_message_date" href="https://t.me/ai_lab/200"><time datetime="2026-08-09T11:00:00+00:00"></time></a>
                </div>
            """,
            "https://t.me/s/ai_lab?before=200": """
                <div class="tgme_widget_message js-widget_message" data-post="ai_lab/180">
                  <div class="tgme_widget_message_text js-message_text">Old AI company transformation.</div>
                  <a class="tgme_widget_message_date" href="https://t.me/ai_lab/180"><time datetime="2026-04-01T11:00:00+00:00"></time></a>
                </div>
            """,
        }
        requested: list[str] = []

        def fake_fetch(url: str, timeout_seconds: int) -> str:
            requested.append(url)
            return pages[url]

        posts = fetch_telegram_preview_posts(
            "@ai_lab",
            window_start=datetime(2026, 5, 10, tzinfo=timezone.utc),
            max_pages=4,
            sleep_seconds=0,
            fetch_url=fake_fetch,
        )

        self.assertEqual([post.message_id for post in posts], [200])
        self.assertEqual(requested, ["https://t.me/s/ai_lab", "https://t.me/s/ai_lab?before=200"])

    def test_build_source_packet_uses_read_only_db_fake_live_fetch_and_private_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agent.db"
            output_root = Path(tmpdir) / "output"
            self._seed_db(db_path)

            def fake_live_fetcher(channel_username: str, **kwargs):
                return [
                    TelegramPost(
                        channel_username=channel_username,
                        message_id=201,
                        posted_at="2026-08-08T09:00:00Z",
                        source_url="https://t.me/ai_lab/201",
                        text=(
                            "Google описывает AI трансформацию компании: рост productivity, "
                            "но без прироста там, где процессы и данные не готовы."
                        ),
                        views=2000,
                        reactions=21,
                    )
                ]

            payload = build_ai_transformation_source_packet(
                db_path=db_path,
                output_root=output_root,
                fetch_live=True,
                live_fetcher=fake_live_fetcher,
                now=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
                days=92,
                top_channels=1,
                max_live_pages=2,
            )
            markdown = Path(payload["outputs"]["markdown_path"]).read_text(encoding="utf-8")
            cached = json.loads(Path(payload["outputs"]["json_path"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "ai_transformation_source_packet.v1")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["source_counts"]["live_preview_posts"], 1)
        self.assertEqual(payload["source_counts"]["relevant_posts"], 2)
        self.assertFalse(payload["privacy"]["production_db_write"])
        self.assertFalse(payload["privacy"]["provider_egress"])
        self.assertIn("AI transformation source packet", markdown)
        self.assertIn("production_db_write=false", markdown)
        self.assertIn("https://t.me/ai_lab/201", markdown)
        self.assertEqual(cached["outputs"]["markdown_path"], payload["outputs"]["markdown_path"])

    def _seed_db(self, db_path: Path) -> None:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                CREATE TABLE reaction_sync_state (
                    channel_username TEXT,
                    message_id INTEGER,
                    emoji TEXT,
                    action_key TEXT,
                    applied_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE raw_posts (
                    id INTEGER PRIMARY KEY,
                    channel_username TEXT,
                    message_id INTEGER,
                    posted_at TEXT,
                    text TEXT,
                    media_caption TEXT,
                    message_url TEXT,
                    view_count INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY,
                    raw_post_id INTEGER,
                    channel_username TEXT,
                    posted_at TEXT,
                    content TEXT
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO reaction_sync_state (
                    channel_username, message_id, emoji, action_key, applied_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("@ai_lab", 101, "👍", "liked", "2026-08-09T10:00:00Z"),
                    ("@ai_lab", 102, "🔥", "liked", "2026-08-09T11:00:00Z"),
                    ("@other", 77, "👍", "liked", "2026-08-09T12:00:00Z"),
                ],
            )
            connection.execute(
                """
                INSERT INTO raw_posts (
                    id, channel_username, message_id, posted_at, text,
                    media_caption, message_url, view_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "@ai_lab",
                    101,
                    "2026-08-07T09:00:00Z",
                    "Microsoft AI внедрение в компании дало рост productivity, но часть процессов не работает.",
                    None,
                    "https://t.me/ai_lab/101",
                    1000,
                ),
            )
            connection.execute(
                """
                INSERT INTO posts (raw_post_id, channel_username, posted_at, content)
                VALUES (?, ?, ?, ?)
                """,
                (
                    1,
                    "@ai_lab",
                    "2026-08-07T09:00:00Z",
                    "Microsoft AI внедрение в компании дало рост productivity, но часть процессов не работает.",
                ),
            )
            connection.commit()


if __name__ == "__main__":
    unittest.main()
