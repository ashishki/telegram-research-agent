import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.migrate import run_migrations
from output.opportunity_seed_export import export_opportunity_seeds


class TestOpportunitySeedExport(unittest.TestCase):
    def test_exports_demand_surface_seed_for_radar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            posted_at = "2026-05-23T10:00:00Z"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO raw_posts (
                        id, channel_username, channel_id, message_id, posted_at, text,
                        media_type, media_caption, forward_from, view_count, message_url,
                        raw_json, ingested_at, image_description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "@its_capitan",
                        10,
                        100,
                        posted_at,
                        "Owners ask how to make Telegram channel content searchable for SEO.",
                        None,
                        None,
                        None,
                        500,
                        "https://t.me/its_capitan/100",
                        "{}",
                        posted_at,
                        None,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO posts (
                        id, raw_post_id, channel_username, posted_at, content,
                        url_count, has_code, language_detected, word_count, normalized_at,
                        bucket, signal_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        1,
                        "@its_capitan",
                        posted_at,
                        "Owners ask how to make Telegram channel content searchable for SEO.",
                        0,
                        0,
                        "en",
                        10,
                        posted_at,
                        "noise",
                        0.2,
                    ),
                )
                connection.commit()

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                Settings(
                    db_path=db_path,
                    llm_api_key="",
                    model_provider="anthropic",
                    telegram_session_path="",
                ),
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 5, 25, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(result.seed_count, 1)
            self.assertEqual(seeds[0]["mvp_shape"], "Telegram Channel SEO Site Generator")
            self.assertIn("creator_content_gap", seeds[0]["demand_surfaces"])
            self.assertEqual(seeds[0]["source_url"], "https://t.me/its_capitan/100")


if __name__ == "__main__":
    unittest.main()
