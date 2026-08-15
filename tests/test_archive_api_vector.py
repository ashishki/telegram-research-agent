import sqlite3
from pathlib import Path

import pytest

from db.archive_api_vector import (
    ApiEmbeddingBatch,
    ArchiveApiVectorIndexError,
    build_archive_api_vector_index,
    search_archive_api_vector_index,
)


def _seed_archive(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
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
            ingested_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z',
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
            normalized_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z'
        );
        """
    )
    rows = [
        (
            1,
            "Reliability evals need grounded citations, holdout gates, and traceable claim evidence.",
            "https://t.me/eval/1",
        ),
        (
            2,
            "Garden planning compares soil, tomatoes, watering schedules, and sunlight.",
            "https://t.me/garden/2",
        ),
    ]
    for post_id, content, url in rows:
        connection.execute(
            "INSERT INTO raw_posts(id, channel_username, channel_id, message_id, posted_at, message_url) VALUES (?, ?, ?, ?, ?, ?)",
            (post_id + 1000, "@source", -100, post_id, f"2026-08-0{post_id}T10:00:00Z", url),
        )
        connection.execute(
            "INSERT INTO posts(id, raw_post_id, channel_username, posted_at, content, language_detected, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_id, post_id + 1000, "@source", f"2026-08-0{post_id}T10:00:00Z", content, "en", len(content.split())),
        )
    connection.commit()
    return connection


def _fake_embedder(texts, model):
    vectors = []
    for text in texts:
        lower = str(text).casefold()
        vectors.append(
            [
                1.0 if any(token in lower for token in ("eval", "citation", "ground", "holdout")) else 0.0,
                1.0 if any(token in lower for token in ("garden", "tomato", "soil", "sunlight")) else 0.0,
            ]
        )
    return ApiEmbeddingBatch(
        vectors=vectors,
        model=model,
        prompt_tokens=sum(len(str(text).split()) for text in texts),
        total_tokens=sum(len(str(text).split()) for text in texts),
        duration_ms=1,
    )


def test_api_vector_index_uses_sidecar_and_fake_embedder(tmp_path):
    connection = _seed_archive(tmp_path / "agent.db")
    index_path = tmp_path / "api-vector.sqlite"

    payload = build_archive_api_vector_index(
        connection,
        index_path=index_path,
        force=True,
        embedder=_fake_embedder,
        require_approval=False,
    )

    assert payload["status"] == "ok"
    assert payload["inserted"] == 2
    assert payload["privacy"]["provider_egress"] is True
    assert payload["privacy"]["canonical_db_mutated"] is False

    results = search_archive_api_vector_index(
        index_path=index_path,
        query="How should I evaluate grounded citations?",
        embedder=_fake_embedder,
        require_approval=False,
    )

    assert results[0].post_id == 1
    assert results[0].retrieval_mode == "api_vector_archive"


def test_api_vector_requires_explicit_approval(tmp_path, monkeypatch):
    connection = _seed_archive(tmp_path / "agent.db")
    monkeypatch.delenv("PRM_API_EMBEDDINGS_APPROVED", raising=False)

    with pytest.raises(ArchiveApiVectorIndexError):
        build_archive_api_vector_index(
            connection,
            index_path=tmp_path / "api-vector.sqlite",
            embedder=_fake_embedder,
        )
