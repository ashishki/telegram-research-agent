from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from db.archive_documents import DEFAULT_CHUNK_MAX_CHARS, archive_documents_for_row
from db.archive_search import (
    ArchiveSearchFilters,
    ArchiveSearchResult,
    search_telegram_archive,
)


ARCHIVE_VECTOR_INDEX_SCHEMA_VERSION = "archive_vector_index.v1"
LOCAL_EMBEDDING_MODEL = "local_hashing_text_vector.v1"
DEFAULT_VECTOR_DIM = 2048
DEFAULT_MAX_INDEX_ROWS = 50_000
RRF_K = 60
_VECTOR_ROW_CACHE: dict[tuple[str, int, int], list[tuple[dict[str, Any], dict[int, float]]]] = {}


class ArchiveVectorIndexError(ValueError):
    """Raised when a local archive vector index cannot be used safely."""


def build_archive_vector_index(
    connection: sqlite3.Connection,
    *,
    index_path: str | Path,
    limit: int = 0,
    force: bool = False,
    vector_dim: int = DEFAULT_VECTOR_DIM,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> dict[str, Any]:
    """Build or refresh a local sidecar vector index from retained archive posts.

    This never mutates canonical `raw_posts`, `posts`, or `posts_fts` rows. The
    index is a disposable SQLite sidecar: it stores stable archive document IDs,
    bounded snippets, local hashed vectors, and metadata needed for filtering.
    """
    if not _table_exists(connection, "posts") or not _table_exists(connection, "raw_posts"):
        raise ArchiveVectorIndexError("archive posts/raw_posts tables are required")
    clean_limit = max(0, int(limit or 0))
    clean_dim = max(128, min(16_384, int(vector_dim or DEFAULT_VECTOR_DIM)))
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    rows = _archive_rows(connection, limit=clean_limit)
    sidecar = sqlite3.connect(path)
    try:
        sidecar.row_factory = sqlite3.Row
        _ensure_index_schema(sidecar)
        if force:
            sidecar.execute("DELETE FROM archive_vector_documents")
        existing = {
            str(row["archive_document_id"]): str(row["content_hash"])
            for row in sidecar.execute(
                "SELECT archive_document_id, content_hash FROM archive_vector_documents"
            ).fetchall()
        }

        seen: set[str] = set()
        inserted = updated = skipped = 0
        for row in rows:
            row_dict = _row_to_mapping(row)
            documents, exclusion = archive_documents_for_row(row_dict, chunk_max_chars=chunk_max_chars)
            if exclusion is not None:
                continue
            metadata = _row_metadata(connection, row_dict)
            for document in documents:
                seen.add(document.archive_document_id)
                if existing.get(document.archive_document_id) == document.content_hash:
                    skipped += 1
                    continue
                vector = _embed_text(document.content, dim=clean_dim)
                sidecar.execute(
                    """
                    INSERT INTO archive_vector_documents (
                        archive_document_id,
                        post_archive_document_id,
                        post_id,
                        raw_post_id,
                        channel_username,
                        channel_id,
                        message_id,
                        posted_at,
                        source_url,
                        language,
                        snippet,
                        content_hash,
                        duplicate_cluster_id,
                        repost_cluster_id,
                        chunk_index,
                        chunk_count,
                        reaction_count,
                        tag_count,
                        reactions_json,
                        tags_json,
                        project_names_json,
                        vector_dim,
                        vector_json,
                        indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(archive_document_id) DO UPDATE SET
                        post_archive_document_id=excluded.post_archive_document_id,
                        post_id=excluded.post_id,
                        raw_post_id=excluded.raw_post_id,
                        channel_username=excluded.channel_username,
                        channel_id=excluded.channel_id,
                        message_id=excluded.message_id,
                        posted_at=excluded.posted_at,
                        source_url=excluded.source_url,
                        language=excluded.language,
                        snippet=excluded.snippet,
                        content_hash=excluded.content_hash,
                        duplicate_cluster_id=excluded.duplicate_cluster_id,
                        repost_cluster_id=excluded.repost_cluster_id,
                        chunk_index=excluded.chunk_index,
                        chunk_count=excluded.chunk_count,
                        reaction_count=excluded.reaction_count,
                        tag_count=excluded.tag_count,
                        reactions_json=excluded.reactions_json,
                        tags_json=excluded.tags_json,
                        project_names_json=excluded.project_names_json,
                        vector_dim=excluded.vector_dim,
                        vector_json=excluded.vector_json,
                        indexed_at=excluded.indexed_at
                    """,
                    (
                        document.archive_document_id,
                        document.post_archive_document_id,
                        document.post_id,
                        document.raw_post_id,
                        document.channel_username,
                        document.channel_id,
                        document.message_id,
                        document.posted_at,
                        document.source_url,
                        document.language,
                        _bounded_snippet(document.content),
                        document.content_hash,
                        document.duplicate_cluster_id,
                        document.repost_cluster_id,
                        document.chunk_index,
                        document.chunk_count,
                        metadata["reaction_count"],
                        metadata["tag_count"],
                        json.dumps(metadata["reactions"], ensure_ascii=False, sort_keys=True),
                        json.dumps(metadata["tags"], ensure_ascii=False, sort_keys=True),
                        json.dumps(metadata["project_names"], ensure_ascii=False, sort_keys=True),
                        clean_dim,
                        _dump_vector(vector),
                        indexed_at,
                    ),
                )
                if document.archive_document_id in existing:
                    updated += 1
                else:
                    inserted += 1
        # A bounded diagnostic build must not prune documents outside the scan
        # window. Stale cleanup is safe only after a full source scan.
        deleted = _delete_stale(sidecar, seen) if clean_limit <= 0 else 0
        _set_metadata(sidecar, "schema_version", ARCHIVE_VECTOR_INDEX_SCHEMA_VERSION)
        _set_metadata(sidecar, "embedding_model", LOCAL_EMBEDDING_MODEL)
        _set_metadata(sidecar, "vector_dim", str(clean_dim))
        _set_metadata(sidecar, "updated_at", indexed_at)
        _set_metadata(sidecar, "source", "local_sqlite_sidecar")
        sidecar.commit()
    finally:
        sidecar.close()
    _clear_vector_cache(path)

    return {
        "schema_version": ARCHIVE_VECTOR_INDEX_SCHEMA_VERSION,
        "status": "ok",
        "index_path": str(path),
        "embedding_model": LOCAL_EMBEDDING_MODEL,
        "vector_dim": clean_dim,
        "source_rows_scanned": len(rows),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "indexed_at": indexed_at,
        "privacy": {
            "embedding_provider": "local",
            "provider_egress": False,
            "raw_telegram_corpus_egress": False,
            "canonical_db_mutated": False,
            "sidecar_write": True,
        },
    }


def search_archive_vector_index(
    *,
    index_path: str | Path,
    query: str,
    filters: ArchiveSearchFilters | Mapping[str, object] | None = None,
    limit: int = 10,
    max_scan_rows: int = DEFAULT_MAX_INDEX_ROWS,
) -> list[ArchiveSearchResult]:
    clean_query = " ".join(str(query or "").split())
    if not clean_query:
        raise ArchiveVectorIndexError("query is required")
    path = Path(index_path)
    if not path.exists():
        raise ArchiveVectorIndexError("vector index sidecar is missing")
    normalized_filters = _coerce_filters(filters)
    clean_limit = max(1, int(limit or 10))
    clean_scan = max(clean_limit, min(DEFAULT_MAX_INDEX_ROWS, int(max_scan_rows or DEFAULT_MAX_INDEX_ROWS)))

    sidecar = sqlite3.connect(path)
    try:
        sidecar.row_factory = sqlite3.Row
        _validate_index(sidecar)
        vector_dim = int(_metadata(sidecar, "vector_dim") or DEFAULT_VECTOR_DIM)
        query_vector = _embed_text(clean_query, dim=vector_dim)
        if not query_vector:
            return []
        rows = _load_cached_candidate_rows(path, sidecar, normalized_filters, limit=clean_scan)
    finally:
        sidecar.close()

    scored: list[tuple[float, Mapping[str, Any]]] = []
    for row, vector in rows:
        if not _row_matches_filters(row, normalized_filters):
            continue
        score = _dot(query_vector, vector)
        if score <= 0:
            continue
        scored.append((score, row))
    scored.sort(
        key=lambda pair: (
            pair[0],
            str(pair[1]["posted_at"] or ""),
            int(pair[1]["post_id"] or 0),
        ),
        reverse=True,
    )
    return [
        _result_from_vector_row(row, score=score)
        for score, row in scored[:clean_limit]
    ]


def search_telegram_archive_hybrid(
    connection: sqlite3.Connection,
    query: str,
    *,
    vector_index_path: str | Path,
    filters: ArchiveSearchFilters | Mapping[str, object] | None = None,
    limit: int = 10,
    vector_policy: str = "fallback_on_fts_miss",
) -> list[ArchiveSearchResult]:
    """Search with FTS-first hybrid retrieval and optional full fusion."""
    clean_limit = max(1, int(limit or 10))
    clean_policy = str(vector_policy or "fallback_on_fts_miss").strip()
    if clean_policy not in {"fallback_on_fts_miss", "always"}:
        raise ArchiveVectorIndexError("vector_policy must be fallback_on_fts_miss or always")
    fts_results: list[ArchiveSearchResult] = []
    vector_results: list[ArchiveSearchResult] = []
    try:
        fts_results = search_telegram_archive(
            connection,
            query,
            filters=filters,
            limit=clean_limit,
        )
    except Exception:
        fts_results = []
    if fts_results and clean_policy == "fallback_on_fts_miss":
        return _merge_fts_and_vector(fts_results, [], limit=clean_limit)
    try:
        vector_results = search_archive_vector_index(
            index_path=vector_index_path,
            query=query,
            filters=filters,
            limit=clean_limit,
        )
    except ArchiveVectorIndexError:
        vector_results = []
    return _merge_fts_and_vector(fts_results, vector_results, limit=clean_limit)


def _ensure_index_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS archive_vector_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS archive_vector_documents (
            archive_document_id TEXT PRIMARY KEY,
            post_archive_document_id TEXT NOT NULL,
            post_id INTEGER NOT NULL,
            raw_post_id INTEGER NOT NULL,
            channel_username TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            posted_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            language TEXT NOT NULL,
            snippet TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            duplicate_cluster_id TEXT,
            repost_cluster_id TEXT,
            chunk_index INTEGER,
            chunk_count INTEGER NOT NULL,
            reaction_count INTEGER NOT NULL DEFAULT 0,
            tag_count INTEGER NOT NULL DEFAULT 0,
            reactions_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(reactions_json)),
            tags_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(tags_json)),
            project_names_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(project_names_json)),
            vector_dim INTEGER NOT NULL,
            vector_json TEXT NOT NULL CHECK(json_valid(vector_json)),
            indexed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_archive_vector_channel
            ON archive_vector_documents(channel_username);
        CREATE INDEX IF NOT EXISTS idx_archive_vector_posted
            ON archive_vector_documents(posted_at);
        CREATE INDEX IF NOT EXISTS idx_archive_vector_post
            ON archive_vector_documents(post_id);
        """
    )


def _validate_index(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "archive_vector_documents"):
        raise ArchiveVectorIndexError("vector index table is missing")
    if _metadata(connection, "schema_version") != ARCHIVE_VECTOR_INDEX_SCHEMA_VERSION:
        raise ArchiveVectorIndexError("vector index schema_version is invalid")
    if _metadata(connection, "embedding_model") != LOCAL_EMBEDDING_MODEL:
        raise ArchiveVectorIndexError("vector index embedding_model is invalid")


def _archive_rows(connection: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    sql = """
        SELECT
            p.id AS post_id,
            p.raw_post_id,
            p.channel_username,
            p.posted_at,
            p.content,
            p.language_detected,
            r.channel_id,
            r.message_id,
            r.message_url,
            r.forward_from
        FROM posts p
        JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.content IS NOT NULL
          AND length(trim(p.content)) > 0
        ORDER BY p.id ASC
    """
    params: tuple[object, ...] = ()
    if limit > 0:
        sql += " LIMIT ?"
        params = (limit,)
    return connection.execute(sql, params).fetchall()


def _row_metadata(connection: sqlite3.Connection, row: Mapping[str, object]) -> dict[str, Any]:
    post_id = int(row.get("post_id") or 0)
    reactions = _list_for_post(connection, "signal_feedback", "feedback", post_id)
    tags = _list_for_post(connection, "user_post_tags", "tag", post_id)
    project_names = _project_names_for_post(connection, post_id)
    return {
        "reaction_count": len(reactions),
        "tag_count": len(tags),
        "reactions": reactions,
        "tags": tags,
        "project_names": project_names,
    }


def _list_for_post(connection: sqlite3.Connection, table_name: str, column_name: str, post_id: int) -> list[str]:
    if not _table_exists(connection, table_name):
        return []
    rows = connection.execute(
        f"SELECT DISTINCT {column_name} FROM {table_name} WHERE post_id = ? ORDER BY {column_name}",
        (post_id,),
    ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


def _project_names_for_post(connection: sqlite3.Connection, post_id: int) -> list[str]:
    if not _table_exists(connection, "post_project_links") or not _table_exists(connection, "projects"):
        return []
    rows = connection.execute(
        """
        SELECT DISTINCT pr.name
        FROM post_project_links ppl
        JOIN projects pr ON pr.id = ppl.project_id
        WHERE ppl.post_id = ?
        ORDER BY pr.name
        """,
        (post_id,),
    ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


def _load_candidate_rows(
    connection: sqlite3.Connection,
    filters: ArchiveSearchFilters,
    *,
    limit: int,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[object] = []
    if filters.channel_usernames:
        where.append("channel_username IN (" + ",".join("?" for _ in filters.channel_usernames) + ")")
        params.extend(filters.channel_usernames)
    if filters.languages:
        where.append("language IN (" + ",".join("?" for _ in filters.languages) + ")")
        params.extend(filters.languages)
    if filters.date_from:
        where.append("posted_at >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        where.append("posted_at < ?")
        params.append(filters.date_to)
    sql = "SELECT * FROM archive_vector_documents"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY posted_at DESC, post_id DESC LIMIT ?"
    return connection.execute(sql, [*params, limit]).fetchall()


def _load_cached_candidate_rows(
    path: Path,
    connection: sqlite3.Connection,
    filters: ArchiveSearchFilters,
    *,
    limit: int,
) -> list[tuple[dict[str, Any], dict[int, float]]]:
    cache_key = _vector_cache_key(path)
    cached = _VECTOR_ROW_CACHE.get(cache_key)
    if cached is None:
        rows = connection.execute(
            "SELECT * FROM archive_vector_documents ORDER BY posted_at DESC, post_id DESC LIMIT ?",
            (DEFAULT_MAX_INDEX_ROWS,),
        ).fetchall()
        cached = [({key: row[key] for key in row.keys()}, _load_vector(str(row["vector_json"] or ""))) for row in rows]
        _VECTOR_ROW_CACHE.clear()
        _VECTOR_ROW_CACHE[cache_key] = cached
    selected: list[tuple[dict[str, Any], dict[int, float]]] = []
    for row, vector in cached:
        if not _row_matches_primary_filters(row, filters):
            continue
        selected.append((row, vector))
        if len(selected) >= limit:
            break
    return selected


def _row_matches_primary_filters(row: Mapping[str, Any], filters: ArchiveSearchFilters) -> bool:
    if filters.channel_usernames and str(row["channel_username"]) not in filters.channel_usernames:
        return False
    if filters.languages and str(row["language"]) not in filters.languages:
        return False
    if filters.date_from and str(row["posted_at"]) < filters.date_from:
        return False
    if filters.date_to and str(row["posted_at"]) >= filters.date_to:
        return False
    return True


def _vector_cache_key(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))


def _clear_vector_cache(path: Path) -> None:
    resolved = str(path.resolve())
    for key in list(_VECTOR_ROW_CACHE):
        if key[0] == resolved:
            _VECTOR_ROW_CACHE.pop(key, None)


def _row_matches_filters(row: Mapping[str, Any], filters: ArchiveSearchFilters) -> bool:
    if filters.reacted_only and int(row["reaction_count"] or 0) <= 0:
        return False
    if filters.reactions and not set(filters.reactions).intersection(_json_strings(row["reactions_json"])):
        return False
    if filters.tags and not set(filters.tags).intersection(_json_strings(row["tags_json"])):
        return False
    if filters.project_names and not set(filters.project_names).intersection(_json_strings(row["project_names_json"])):
        return False
    return True


def _result_from_vector_row(row: Mapping[str, Any], *, score: float) -> ArchiveSearchResult:
    return ArchiveSearchResult(
        archive_document_id=str(row["archive_document_id"]),
        post_archive_document_id=str(row["post_archive_document_id"]),
        post_id=int(row["post_id"]),
        raw_post_id=int(row["raw_post_id"]),
        channel_username=str(row["channel_username"]),
        channel_id=int(row["channel_id"]),
        message_id=int(row["message_id"]),
        posted_at=str(row["posted_at"]),
        source_url=str(row["source_url"]),
        language=str(row["language"]),
        snippet=str(row["snippet"] or ""),
        rank=-float(score),
        content_hash=str(row["content_hash"]),
        duplicate_cluster_id=str(row["duplicate_cluster_id"]) if row["duplicate_cluster_id"] is not None else None,
        repost_cluster_id=str(row["repost_cluster_id"]) if row["repost_cluster_id"] is not None else None,
        chunk_index=int(row["chunk_index"]) if row["chunk_index"] is not None else None,
        chunk_count=int(row["chunk_count"] or 1),
        reaction_count=int(row["reaction_count"] or 0),
        tag_count=int(row["tag_count"] or 0),
        project_names=tuple(_json_strings(row["project_names_json"])),
        retrieval_mode="local_vector_archive",
        semantic_score=round(float(score), 6),
    )


def _merge_fts_and_vector(
    fts_results: Sequence[ArchiveSearchResult],
    vector_results: Sequence[ArchiveSearchResult],
    *,
    limit: int,
) -> list[ArchiveSearchResult]:
    entries: dict[str, dict[str, Any]] = {}
    for rank, result in enumerate(fts_results, start=1):
        entries[result.archive_document_id] = {
            "result": result,
            "fts_rank": rank,
            "vector_rank": None,
            "score": _rrf(rank),
        }
    for rank, result in enumerate(vector_results, start=1):
        entry = entries.setdefault(
            result.archive_document_id,
            {"result": result, "fts_rank": None, "vector_rank": None, "score": 0.0},
        )
        entry["vector_rank"] = rank
        entry["score"] += _rrf(rank)
        if entry["fts_rank"] is None:
            entry["result"] = result
    ranked = sorted(
        entries.values(),
        key=lambda entry: (
            float(entry["score"]),
            entry["fts_rank"] is not None and entry["vector_rank"] is not None,
            str(entry["result"].posted_at or ""),
        ),
        reverse=True,
    )
    merged = []
    for entry in ranked[: max(1, int(limit or 10))]:
        result = entry["result"]
        mode = (
            "hybrid_fts_vector"
            if entry.get("fts_rank") is not None and entry.get("vector_rank") is not None
            else "hybrid_fts_only"
            if entry.get("fts_rank") is not None
            else "hybrid_vector_only"
        )
        merged.append(
            replace(
                result,
                rank=-round(float(entry["score"]), 8),
                retrieval_mode=mode,
                fts_rank=entry.get("fts_rank"),
                vector_rank=entry.get("vector_rank"),
                fusion_score=round(float(entry["score"]), 8),
            )
        )
    return merged


def _embed_text(text: str, *, dim: int) -> dict[int, float]:
    features = list(_features(text))
    if not features:
        return {}
    counts: dict[int, float] = {}
    for feature in features:
        index = _stable_index(feature, dim=dim)
        counts[index] = counts.get(index, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm <= 0:
        return {}
    return {index: value / norm for index, value in counts.items()}


def _features(text: str) -> Iterable[str]:
    normalized = " ".join(str(text or "").casefold().split())
    tokens = [
        token
        for token in _simple_tokens(normalized)
        if len(token) >= 2
    ]
    for token in tokens:
        yield f"w:{token}"
    for left, right in zip(tokens, tokens[1:]):
        yield f"b:{left}_{right}"
    compact = "".join(tokens)
    for size in (3, 4, 5):
        if len(compact) < size:
            continue
        for index in range(0, len(compact) - size + 1):
            yield f"c{size}:{compact[index:index + size]}"


def _simple_tokens(text: str) -> list[str]:
    token = []
    tokens: list[str] = []
    for char in text:
        if char.isalnum() or char in {"_", "-", "+"}:
            token.append(char)
        elif token:
            tokens.append("".join(token))
            token = []
    if token:
        tokens.append("".join(token))
    return tokens


def _stable_index(feature: str, *, dim: int) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _dump_vector(vector: Mapping[int, float]) -> str:
    return json.dumps([[int(index), round(float(value), 8)] for index, value in sorted(vector.items())], separators=(",", ":"))


def _load_vector(raw: str) -> dict[int, float]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result: dict[int, float] = {}
    if not isinstance(data, list):
        return result
    for pair in data:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        try:
            result[int(pair[0])] = float(pair[1])
        except (TypeError, ValueError):
            continue
    return result


def _dot(left: Mapping[int, float], right: Mapping[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(float(value) * float(right.get(index, 0.0)) for index, value in left.items())


def _rrf(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / (RRF_K + int(rank))


def _bounded_snippet(text: str, limit: int = 240) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _delete_stale(connection: sqlite3.Connection, live_ids: set[str]) -> int:
    rows = connection.execute("SELECT archive_document_id FROM archive_vector_documents").fetchall()
    stale = [str(row[0]) for row in rows if str(row[0]) not in live_ids]
    if stale:
        connection.executemany(
            "DELETE FROM archive_vector_documents WHERE archive_document_id = ?",
            [(archive_document_id,) for archive_document_id in stale],
        )
    return len(stale)


def _coerce_filters(filters: ArchiveSearchFilters | Mapping[str, object] | None) -> ArchiveSearchFilters:
    if filters is None:
        return ArchiveSearchFilters()
    if isinstance(filters, ArchiveSearchFilters):
        return filters
    return ArchiveSearchFilters(
        channel_usernames=tuple(_string_list(filters.get("channel_usernames") or filters.get("channels"))),
        languages=tuple(_string_list(filters.get("languages") or filters.get("language"))),
        date_from=_optional_string(filters.get("date_from")),
        date_to=_optional_string(filters.get("date_to")),
        reacted_only=bool(filters.get("reacted_only") or False),
        reactions=tuple(_string_list(filters.get("reactions") or filters.get("reaction"))),
        tags=tuple(_string_list(filters.get("tags") or filters.get("tag"))),
        project_names=tuple(_string_list(filters.get("project_names") or filters.get("project_name"))),
    )


def _metadata(connection: sqlite3.Connection, key: str) -> str:
    if not _table_exists(connection, "archive_vector_metadata"):
        return ""
    row = connection.execute(
        "SELECT value FROM archive_vector_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row[0] if row else "")


def _set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO archive_vector_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _json_strings(raw: object) -> list[str]:
    try:
        data = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(value).strip() for value in data if str(value).strip()]


def _string_list(value: object) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)  # type: ignore[arg-type]
        except TypeError:
            values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _row_to_mapping(row: sqlite3.Row | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(row, Mapping):
        return row
    return {key: row[key] for key in row.keys()}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None
