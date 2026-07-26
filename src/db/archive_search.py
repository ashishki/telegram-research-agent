from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Mapping, Sequence

from db.archive_documents import (
    DEFAULT_CHUNK_MAX_CHARS,
    ArchiveDocument,
    archive_documents_for_row,
)


TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_-]{1,}")


class ArchiveSearchError(ValueError):
    """Raised when an archive search request cannot be executed safely."""


@dataclass(frozen=True)
class ArchiveSearchFilters:
    channel_usernames: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    date_from: str | None = None
    date_to: str | None = None
    reacted_only: bool = False
    reactions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    project_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArchiveSearchResult:
    archive_document_id: str
    post_archive_document_id: str
    post_id: int
    raw_post_id: int
    channel_username: str
    channel_id: int
    message_id: int
    posted_at: str
    source_url: str
    language: str
    snippet: str
    rank: float
    content_hash: str
    duplicate_cluster_id: str | None
    repost_cluster_id: str | None
    chunk_index: int | None
    chunk_count: int
    reaction_count: int
    tag_count: int
    project_names: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "archive_document_id": self.archive_document_id,
            "post_archive_document_id": self.post_archive_document_id,
            "post_id": self.post_id,
            "raw_post_id": self.raw_post_id,
            "channel_username": self.channel_username,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "posted_at": self.posted_at,
            "source_url": self.source_url,
            "language": self.language,
            "snippet": self.snippet,
            "rank": self.rank,
            "content_hash": self.content_hash,
            "duplicate_cluster_id": self.duplicate_cluster_id,
            "repost_cluster_id": self.repost_cluster_id,
            "chunk_index": self.chunk_index,
            "chunk_count": self.chunk_count,
            "reaction_count": self.reaction_count,
            "tag_count": self.tag_count,
            "project_names": list(self.project_names),
        }


def search_telegram_archive(
    connection: sqlite3.Connection,
    query: str,
    *,
    filters: ArchiveSearchFilters | Mapping[str, object] | None = None,
    limit: int = 10,
    snippet_tokens: int = 32,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> list[ArchiveSearchResult]:
    """Search retained Telegram archive posts through persistent SQLite FTS.

    The function is read-only from the caller's perspective: it performs SELECTs
    over canonical archive tables and returns bounded snippets with stable
    archive document identity. It does not require Knowledge Atoms.
    """
    normalized_filters = _coerce_filters(filters)
    clean_limit = max(1, int(limit or 10))
    clean_snippet_tokens = max(8, min(80, int(snippet_tokens or 32)))

    fts_query = build_fts_query(query, operator="AND")
    fallback_query = build_fts_query(query, operator="OR")
    rows = _fetch_search_rows(
        connection,
        fts_query=fts_query,
        filters=normalized_filters,
        limit=clean_limit,
        snippet_tokens=clean_snippet_tokens,
    )
    if not rows and fallback_query != fts_query:
        rows = _fetch_search_rows(
            connection,
            fts_query=fallback_query,
            filters=normalized_filters,
            limit=clean_limit,
            snippet_tokens=clean_snippet_tokens,
        )

    results: list[ArchiveSearchResult] = []
    for row in rows:
        row_dict = _row_to_mapping(row)
        documents, exclusion = archive_documents_for_row(row_dict, chunk_max_chars=chunk_max_chars)
        if exclusion is not None or not documents:
            continue
        document = _select_document_for_query(documents, query)
        results.append(_result_from_row(row_dict, document=document))
    return results


def build_fts_query(query: str, *, operator: str = "AND") -> str:
    terms = _query_terms(query)
    if not terms:
        raise ArchiveSearchError("query must contain at least one searchable term")
    clean_operator = str(operator or "AND").upper()
    if clean_operator not in {"AND", "OR"}:
        raise ArchiveSearchError("operator must be AND or OR")
    return f" {clean_operator} ".join(f'"{term}"' for term in terms[:16])


def _fetch_search_rows(
    connection: sqlite3.Connection,
    *,
    fts_query: str,
    filters: ArchiveSearchFilters,
    limit: int,
    snippet_tokens: int,
) -> list[sqlite3.Row]:
    where_clauses = ["posts_fts MATCH ?", "p.content IS NOT NULL", "length(trim(p.content)) > 0"]
    params: list[object] = [fts_query]

    _append_in_filter(where_clauses, params, "p.channel_username", filters.channel_usernames)
    _append_in_filter(where_clauses, params, "p.language_detected", filters.languages)
    if filters.date_from:
        where_clauses.append("p.posted_at >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        where_clauses.append("p.posted_at < ?")
        params.append(filters.date_to)
    _append_reaction_filter(connection, where_clauses, params, filters)
    _append_tag_filter(connection, where_clauses, params, filters)
    _append_project_filter(connection, where_clauses, params, filters)

    reaction_count_sql = _reaction_count_sql(connection)
    tag_count_sql = _tag_count_sql(connection)
    project_names_sql = _project_names_sql(connection)
    sql = f"""
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
            r.forward_from,
            snippet(posts_fts, 0, '', '', ' ... ', ?) AS snippet,
            bm25(posts_fts) AS rank,
            {reaction_count_sql} AS reaction_count,
            {tag_count_sql} AS tag_count,
            {project_names_sql} AS project_names
        FROM posts_fts
        JOIN posts p ON p.id = posts_fts.rowid
        JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY rank ASC, p.posted_at DESC, p.id DESC
        LIMIT ?
    """
    return connection.execute(sql, [snippet_tokens, *params, limit]).fetchall()


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for match in TOKEN_RE.finditer(str(query or "")):
        term = match.group(0).casefold()
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


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


def _append_in_filter(
    where_clauses: list[str],
    params: list[object],
    column_name: str,
    values: Sequence[str],
) -> None:
    clean_values = [value for value in values if value]
    if not clean_values:
        return
    placeholders = ",".join("?" * len(clean_values))
    where_clauses.append(f"{column_name} IN ({placeholders})")
    params.extend(clean_values)


def _append_reaction_filter(
    connection: sqlite3.Connection,
    where_clauses: list[str],
    params: list[object],
    filters: ArchiveSearchFilters,
) -> None:
    if not filters.reacted_only and not filters.reactions:
        return
    if not _table_exists(connection, "signal_feedback"):
        where_clauses.append("0")
        return
    clause = "EXISTS (SELECT 1 FROM signal_feedback sf WHERE sf.post_id = p.id"
    if filters.reactions:
        placeholders = ",".join("?" * len(filters.reactions))
        clause += f" AND sf.feedback IN ({placeholders})"
        params.extend(filters.reactions)
    clause += ")"
    where_clauses.append(clause)


def _append_tag_filter(
    connection: sqlite3.Connection,
    where_clauses: list[str],
    params: list[object],
    filters: ArchiveSearchFilters,
) -> None:
    if not filters.tags:
        return
    if not _table_exists(connection, "user_post_tags"):
        where_clauses.append("0")
        return
    placeholders = ",".join("?" * len(filters.tags))
    where_clauses.append(
        f"EXISTS (SELECT 1 FROM user_post_tags upt WHERE upt.post_id = p.id AND upt.tag IN ({placeholders}))"
    )
    params.extend(filters.tags)


def _append_project_filter(
    connection: sqlite3.Connection,
    where_clauses: list[str],
    params: list[object],
    filters: ArchiveSearchFilters,
) -> None:
    if not filters.project_names:
        return
    if not _table_exists(connection, "post_project_links") or not _table_exists(connection, "projects"):
        where_clauses.append("0")
        return
    placeholders = ",".join("?" * len(filters.project_names))
    where_clauses.append(
        f"""
        EXISTS (
            SELECT 1
            FROM post_project_links ppl
            JOIN projects pr ON pr.id = ppl.project_id
            WHERE ppl.post_id = p.id
              AND pr.name IN ({placeholders})
        )
        """
    )
    params.extend(filters.project_names)


def _reaction_count_sql(connection: sqlite3.Connection) -> str:
    if not _table_exists(connection, "signal_feedback"):
        return "0"
    return "COALESCE((SELECT COUNT(*) FROM signal_feedback sf WHERE sf.post_id = p.id), 0)"


def _tag_count_sql(connection: sqlite3.Connection) -> str:
    if not _table_exists(connection, "user_post_tags"):
        return "0"
    return "COALESCE((SELECT COUNT(*) FROM user_post_tags upt WHERE upt.post_id = p.id), 0)"


def _project_names_sql(connection: sqlite3.Connection) -> str:
    if not _table_exists(connection, "post_project_links") or not _table_exists(connection, "projects"):
        return "''"
    return """
        COALESCE((
            SELECT group_concat(pr.name, char(31))
            FROM post_project_links ppl
            JOIN projects pr ON pr.id = ppl.project_id
            WHERE ppl.post_id = p.id
        ), '')
    """


def _select_document_for_query(documents: tuple[ArchiveDocument, ...], query: str) -> ArchiveDocument:
    if len(documents) == 1:
        return documents[0]
    terms = _query_terms(query)
    for document in documents:
        haystack = document.content.casefold()
        if any(term in haystack for term in terms):
            return document
    return documents[0]


def _result_from_row(row: Mapping[str, object], *, document: ArchiveDocument) -> ArchiveSearchResult:
    return ArchiveSearchResult(
        archive_document_id=document.archive_document_id,
        post_archive_document_id=document.post_archive_document_id,
        post_id=document.post_id,
        raw_post_id=document.raw_post_id,
        channel_username=document.channel_username,
        channel_id=document.channel_id,
        message_id=document.message_id,
        posted_at=document.posted_at,
        source_url=document.source_url,
        language=document.language,
        snippet=str(row.get("snippet") or "").strip(),
        rank=float(row.get("rank") or 0.0),
        content_hash=document.content_hash,
        duplicate_cluster_id=document.duplicate_cluster_id,
        repost_cluster_id=document.repost_cluster_id,
        chunk_index=document.chunk_index,
        chunk_count=document.chunk_count,
        reaction_count=int(row.get("reaction_count") or 0),
        tag_count=int(row.get("tag_count") or 0),
        project_names=tuple(value for value in str(row.get("project_names") or "").split(chr(31)) if value),
    )


def _row_to_mapping(row: sqlite3.Row | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(row, Mapping):
        return row
    return {key: row[key] for key in row.keys()}


def _string_list(value: object) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        candidates = [value]
    else:
        try:
            candidates = list(value)  # type: ignore[arg-type]
        except TypeError:
            candidates = [value]
    return [str(candidate).strip() for candidate in candidates if str(candidate).strip()]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
