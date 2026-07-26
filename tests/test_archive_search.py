import sqlite3
import unittest

from db.archive_search import (
    ArchiveSearchError,
    ArchiveSearchFilters,
    build_fts_query,
    search_telegram_archive,
)


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE raw_posts (
            id INTEGER PRIMARY KEY,
            channel_username TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            posted_at TEXT NOT NULL,
            raw_json TEXT NOT NULL DEFAULT '',
            ingested_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z',
            message_url TEXT,
            forward_from TEXT
        );
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY,
            raw_post_id INTEGER NOT NULL UNIQUE,
            channel_username TEXT NOT NULL,
            posted_at TEXT NOT NULL,
            content TEXT NOT NULL,
            url_count INTEGER NOT NULL DEFAULT 0,
            has_code INTEGER NOT NULL DEFAULT 0,
            language_detected TEXT,
            word_count INTEGER NOT NULL DEFAULT 0,
            normalized_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z'
        );
        CREATE VIRTUAL TABLE posts_fts USING fts5(
            content,
            content='posts',
            content_rowid='id'
        );
        CREATE TABLE signal_feedback (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE user_post_tags (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            note TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            keywords TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE post_project_links (
            post_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            relevance_score REAL NOT NULL,
            note TEXT,
            PRIMARY KEY(post_id, project_id)
        );
        """
    )
    return connection


def _insert_post(
    connection: sqlite3.Connection,
    *,
    post_id: int,
    raw_post_id: int | None = None,
    channel_username: str = "@source",
    channel_id: int = -1001,
    message_id: int | None = None,
    posted_at: str = "2026-07-20T10:00:00Z",
    content: str = "Agent review automation works over retained Telegram archive posts.",
    language: str = "ru",
    message_url: str | None = None,
    forward_from: str = "",
) -> None:
    resolved_raw_post_id = raw_post_id or post_id + 100
    resolved_message_id = message_id or post_id + 1000
    resolved_message_url = (
        message_url
        if message_url is not None
        else f"https://t.me/{channel_username.lstrip('@')}/{resolved_message_id}"
    )
    connection.execute(
        """
        INSERT INTO raw_posts (
            id, channel_username, channel_id, message_id, posted_at,
            message_url, forward_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_raw_post_id,
            channel_username,
            channel_id,
            resolved_message_id,
            posted_at,
            resolved_message_url,
            forward_from,
        ),
    )
    connection.execute(
        """
        INSERT INTO posts (
            id, raw_post_id, channel_username, posted_at, content,
            language_detected, word_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            resolved_raw_post_id,
            channel_username,
            posted_at,
            content,
            language,
            len(content.split()),
        ),
    )
    connection.execute(
        "INSERT INTO posts_fts(rowid, content) VALUES (?, ?)",
        (post_id, content),
    )


class TestArchiveSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_connection()

    def tearDown(self) -> None:
        self.connection.close()

    def test_atomless_post_is_searchable_and_returns_required_schema(self):
        _insert_post(self.connection, post_id=1)

        results = search_telegram_archive(self.connection, "agent review", limit=5)

        self.assertEqual(len(results), 1)
        result = results[0].as_dict()
        for field in (
            "archive_document_id",
            "post_archive_document_id",
            "post_id",
            "raw_post_id",
            "channel_username",
            "channel_id",
            "message_id",
            "posted_at",
            "source_url",
            "language",
            "snippet",
            "content_hash",
            "chunk_index",
            "chunk_count",
            "reaction_count",
            "tag_count",
            "project_names",
        ):
            self.assertIn(field, result)
        self.assertEqual(result["archive_document_id"], "tg:-1001:1001")
        self.assertEqual(result["source_url"], "https://t.me/source/1001")
        self.assertEqual(result["channel_username"], "@source")
        self.assertEqual(result["language"], "ru")
        self.assertIn("Agent", result["snippet"])

    def test_metadata_filters_scope_results(self):
        _insert_post(self.connection, post_id=1, channel_username="@source", language="ru")
        _insert_post(
            self.connection,
            post_id=2,
            channel_username="@other",
            channel_id=-1002,
            message_id=2002,
            posted_at="2026-07-10T10:00:00Z",
            language="en",
        )

        results = search_telegram_archive(
            self.connection,
            "agent review",
            filters=ArchiveSearchFilters(
                channel_usernames=("@source",),
                languages=("ru",),
                date_from="2026-07-15T00:00:00Z",
                date_to="2026-07-21T00:00:00Z",
            ),
        )

        self.assertEqual([result.post_id for result in results], [1])

    def test_verbose_query_falls_back_from_strict_and_to_or_match(self):
        _insert_post(self.connection, post_id=1)

        results = search_telegram_archive(self.connection, "find missingword agent review")

        self.assertEqual([result.post_id for result in results], [1])

    def test_reaction_tag_and_project_filters_scope_results(self):
        _insert_post(self.connection, post_id=1)
        _insert_post(self.connection, post_id=2, message_id=2002)
        self.connection.execute(
            "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
            (1, "operator_marked_interesting", "2026-07-20T11:00:00Z"),
        )
        self.connection.execute(
            "INSERT INTO user_post_tags (post_id, tag, note, recorded_at) VALUES (?, ?, ?, ?)",
            (1, "try_in_project", "fixture note", "2026-07-20T11:01:00Z"),
        )
        self.connection.execute(
            "INSERT INTO projects (id, name, description, keywords) VALUES (?, ?, ?, ?)",
            (10, "Eval-Ground-Truth-Lab", "", ""),
        )
        self.connection.execute(
            "INSERT INTO post_project_links (post_id, project_id, relevance_score, note) VALUES (?, ?, ?, ?)",
            (1, 10, 0.9, "fixture link"),
        )

        results = search_telegram_archive(
            self.connection,
            "agent review",
            filters={
                "reacted_only": True,
                "tags": ["try_in_project"],
                "project_names": ["Eval-Ground-Truth-Lab"],
            },
        )

        self.assertEqual([result.post_id for result in results], [1])
        self.assertEqual(results[0].reaction_count, 1)
        self.assertEqual(results[0].tag_count, 1)
        self.assertEqual(results[0].project_names, ("Eval-Ground-Truth-Lab",))

    def test_blank_post_is_excluded_even_if_fts_has_a_row(self):
        _insert_post(self.connection, post_id=1, content="")
        self.connection.execute(
            "INSERT INTO posts_fts(rowid, content) VALUES (?, ?)",
            (99, "agent review"),
        )

        results = search_telegram_archive(self.connection, "agent review")

        self.assertEqual(results, [])

    def test_long_post_returns_matching_chunk_identity_with_source_url(self):
        content = (
            "alpha section establishes context. " * 12
            + "needle archive search term appears here. "
            + "omega section preserves citation. " * 12
        )
        _insert_post(self.connection, post_id=1, content=content)

        results = search_telegram_archive(
            self.connection,
            "needle archive",
            chunk_max_chars=120,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].post_archive_document_id, "tg:-1001:1001")
        self.assertRegex(results[0].archive_document_id, r"^tg:-1001:1001:chunk:[0-9]{4}$")
        self.assertEqual(results[0].source_url, "https://t.me/source/1001")
        self.assertIsNotNone(results[0].chunk_index)
        self.assertGreater(results[0].chunk_count, 1)

    def test_build_fts_query_rejects_unsearchable_input(self):
        with self.assertRaises(ArchiveSearchError):
            build_fts_query(".,?!")


if __name__ == "__main__":
    unittest.main()
