import sqlite3
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

if "anthropic" not in sys.modules:
    anthropic_stub = types.ModuleType("anthropic")
    anthropic_stub.APIConnectionError = RuntimeError
    anthropic_stub.APIStatusError = RuntimeError
    anthropic_stub.APITimeoutError = RuntimeError
    anthropic_stub.RateLimitError = RuntimeError
    anthropic_stub.Anthropic = object
    sys.modules["anthropic"] = anthropic_stub

from output.generate_study_plan import _fetch_topics_this_week, _week_bounds


class WeekBoundsTests(unittest.TestCase):
    def test_week_bounds_returns_iso_strings_with_seven_day_span(self) -> None:
        start_iso, end_iso = _week_bounds("2026-W11")
        self.assertIsInstance(start_iso, str)
        self.assertIsInstance(end_iso, str)

        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        self.assertLess(start, end)
        self.assertEqual(end - start, timedelta(days=7))

    def test_week_bounds_start_is_monday_midnight_utc(self) -> None:
        start_iso, _ = _week_bounds("2026-W11")
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        self.assertEqual(start.tzinfo, timezone.utc)
        self.assertEqual(start.weekday(), 0)
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)

    def test_study_plan_week_query_filter_excludes_end_boundary(self) -> None:
        start_iso, end_iso = _week_bounds("2026-W11")
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE topics (
                id INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT
            );
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                posted_at TEXT NOT NULL
            );
            CREATE TABLE post_topics (
                post_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL
            );
            """
        )
        connection.execute("INSERT INTO topics (id, label, description) VALUES (1, 'Inside Week', 'included')")
        connection.execute("INSERT INTO topics (id, label, description) VALUES (2, 'At Boundary', 'excluded')")
        connection.execute("INSERT INTO posts (id, posted_at) VALUES (1, ?)", (start_iso,))
        connection.execute("INSERT INTO posts (id, posted_at) VALUES (2, ?)", (end_iso,))
        connection.execute("INSERT INTO post_topics (post_id, topic_id) VALUES (1, 1)")
        connection.execute("INSERT INTO post_topics (post_id, topic_id) VALUES (2, 2)")

        rows = _fetch_topics_this_week(connection, "2026-W11")

        self.assertEqual(rows, [{"label": "Inside Week", "description": "included", "post_count": 1}])


if __name__ == "__main__":
    unittest.main()
