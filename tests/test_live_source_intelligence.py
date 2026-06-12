import io
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

from db.migrate import run_migrations  # noqa: E402
from output.live_source_intelligence import build_live_source_intelligence_snapshot  # noqa: E402
from output.source_events import append_source_events, telegram_source_event_from_row  # noqa: E402
import main  # noqa: E402


class TestLiveSourceIntelligence(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _seed_raw_posts(self, connection: sqlite3.Connection) -> None:
        rows = [
            (
                "@source_a",
                11,
                1001,
                "2026-06-10T10:00:00+00:00",
                "Teams keep exporting Telegram threads to CSV for search and SEO archive.",
                "none",
                None,
                None,
                120,
                "https://t.me/source_a/1001",
                "{}",
                "2026-06-10T10:01:00+00:00",
            ),
            (
                "@source_b",
                12,
                1002,
                "2026-06-10T11:00:00+00:00",
                "Teams keep exporting Telegram threads to CSV for search and SEO archive.",
                "none",
                None,
                None,
                90,
                "https://t.me/source_b/1002",
                "{}",
                "2026-06-10T11:01:00+00:00",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO raw_posts (
                channel_username, channel_id, message_id, posted_at, text,
                media_type, media_caption, forward_from, view_count, message_url,
                raw_json, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    def test_source_event_jsonl_contract_and_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "events"
            event = telegram_source_event_from_row(
                {
                    "channel_username": "@source_a",
                    "channel_id": 11,
                    "message_id": 1001,
                    "posted_at": "2026-06-10T10:00:00+00:00",
                    "text": "Teams keep exporting Telegram threads to CSV for search and SEO archive.",
                    "media_type": "none",
                    "media_caption": None,
                    "view_count": 120,
                    "message_url": "https://t.me/source_a/1001",
                    "ingested_at": "2026-06-10T10:01:00+00:00",
                }
            )
            append_source_events([event], event_root=root)
            files = list(root.glob("*.jsonl"))
            self.assertEqual(len(files), 1)
            line = json.loads(files[0].read_text(encoding="utf-8").strip())
            self.assertEqual(line["schema_version"], "source_event.v1")
            self.assertEqual(line["upstream_id"], "telegram:@source_a:1001")

            output = Path(tmpdir) / "snapshot.json"
            result = build_live_source_intelligence_snapshot(
                days=7,
                event_root=root,
                output_path=output,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.event_count, 1)
        self.assertEqual(payload["schema_version"], "live_source_intelligence.v1")
        self.assertTrue(payload["radar_context"]["context_only"])
        self.assertIn("Context only", payload["radar_context"]["summary"])

    def test_live_source_index_cli_backfills_from_sqlite(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                event_root = Path(tmpdir) / "events"
                output = Path(tmpdir) / "snapshot.json"
                with sqlite3.connect(db_path) as connection:
                    self._seed_raw_posts(connection)
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "live-source-index",
                            "--days",
                            "30",
                            "--event-root",
                            str(event_root),
                            "--out",
                            str(output),
                            "--backfill-from-db",
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
                payload = json.loads(output.read_text(encoding="utf-8"))
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("events=2", stdout.getvalue())
        self.assertEqual(payload["events_scanned"], 2)
        self.assertEqual(payload["repeated_claim_candidates"][0]["event_count"], 2)


if __name__ == "__main__":
    unittest.main()
