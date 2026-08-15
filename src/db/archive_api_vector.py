from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from db.archive_documents import DEFAULT_CHUNK_MAX_CHARS, archive_documents_for_row
from db.archive_search import ArchiveSearchFilters, ArchiveSearchResult, search_telegram_archive
from db.archive_vector import (
    _archive_rows,
    _bounded_snippet,
    _coerce_filters,
    _json_strings,
    _merge_fts_and_vector,
    _result_from_vector_row,
    _row_matches_filters,
    _row_matches_primary_filters,
    _row_metadata,
    _row_to_mapping,
    _table_exists,
)

try:  # Optional but already present in the project requirements.
    import numpy as np
except Exception:  # pragma: no cover - exercised only in minimal environments.
    np = None  # type: ignore[assignment]


ARCHIVE_API_VECTOR_INDEX_SCHEMA_VERSION = "archive_api_vector_index.v1"
DEFAULT_EMBEDDING_PROVIDER = "openai"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_MAX_INDEX_ROWS = 50_000
DEFAULT_BATCH_SIZE = 64
DEFAULT_MAX_INPUT_CHARS = 6_000
RRF_K = 60
_API_VECTOR_ROW_CACHE: dict[tuple[str, int, int, str], dict[str, Any]] = {}


class ArchiveApiVectorIndexError(ValueError):
    """Raised when API embedding retrieval cannot be used safely."""


@dataclass(frozen=True, slots=True)
class ApiEmbeddingBatch:
    vectors: list[list[float]]
    model: str
    prompt_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    provider: str = DEFAULT_EMBEDDING_PROVIDER


EmbeddingClient = Callable[[Sequence[str], str], ApiEmbeddingBatch]


def build_archive_api_vector_index(
    connection: sqlite3.Connection,
    *,
    index_path: str | Path,
    limit: int = 0,
    force: bool = False,
    model: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    embedder: EmbeddingClient | None = None,
    require_approval: bool = True,
) -> dict[str, Any]:
    """Build a disposable API-embedding sidecar from retained archive posts.

    Canonical archive tables are opened read-only by callers. This function
    writes only the configured sidecar and sends bounded archive chunks to the
    configured embedding provider when explicitly approved.
    """
    if require_approval and not api_embeddings_approved():
        raise ArchiveApiVectorIndexError("API embeddings require PRM_API_EMBEDDINGS_APPROVED=1")
    if not _table_exists(connection, "posts") or not _table_exists(connection, "raw_posts"):
        raise ArchiveApiVectorIndexError("archive posts/raw_posts tables are required")
    clean_model = _embedding_model(model)
    clean_limit = max(0, int(limit or 0))
    clean_batch_size = max(1, min(128, int(batch_size or DEFAULT_BATCH_SIZE)))
    clean_max_input_chars = max(256, min(32_000, int(max_input_chars or DEFAULT_MAX_INPUT_CHARS)))
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    active_embedder = embedder or _openai_embed_texts

    rows = _archive_rows(connection, limit=clean_limit)
    sidecar = sqlite3.connect(path)
    sidecar.row_factory = sqlite3.Row
    try:
        _ensure_index_schema(sidecar)
        if force:
            sidecar.execute("DELETE FROM archive_api_vector_documents")
        existing = {
            str(row["archive_document_id"]): (str(row["content_hash"]), str(row["embedding_model"]))
            for row in sidecar.execute(
                "SELECT archive_document_id, content_hash, embedding_model FROM archive_api_vector_documents"
            ).fetchall()
        }

        pending: list[tuple[Mapping[str, object], Any, Mapping[str, Any], str]] = []
        seen: set[str] = set()
        inserted = updated = skipped = 0
        prompt_tokens = total_tokens = provider_calls = 0
        provider_duration_ms = 0
        vector_dim = 0
        for row in rows:
            row_dict = _row_to_mapping(row)
            documents, exclusion = archive_documents_for_row(row_dict, chunk_max_chars=chunk_max_chars)
            if exclusion is not None:
                continue
            metadata = _row_metadata(connection, row_dict)
            for document in documents:
                seen.add(document.archive_document_id)
                if existing.get(document.archive_document_id) == (document.content_hash, clean_model):
                    skipped += 1
                    continue
                pending.append((row_dict, document, metadata, document.content[:clean_max_input_chars]))
                if len(pending) >= clean_batch_size:
                    stats = _embed_and_store(
                        sidecar,
                        pending,
                        model=clean_model,
                        embedder=active_embedder,
                        indexed_at=indexed_at,
                        existing=existing,
                    )
                    inserted += stats["inserted"]
                    updated += stats["updated"]
                    prompt_tokens += stats["prompt_tokens"]
                    total_tokens += stats["total_tokens"]
                    provider_calls += 1
                    provider_duration_ms += stats["duration_ms"]
                    vector_dim = stats["vector_dim"] or vector_dim
                    pending = []
        if pending:
            stats = _embed_and_store(
                sidecar,
                pending,
                model=clean_model,
                embedder=active_embedder,
                indexed_at=indexed_at,
                existing=existing,
            )
            inserted += stats["inserted"]
            updated += stats["updated"]
            prompt_tokens += stats["prompt_tokens"]
            total_tokens += stats["total_tokens"]
            provider_calls += 1
            provider_duration_ms += stats["duration_ms"]
            vector_dim = stats["vector_dim"] or vector_dim
        deleted = _delete_stale_api(sidecar, seen) if clean_limit <= 0 else 0
        if not vector_dim:
            vector_dim = int(_metadata(sidecar, "vector_dim") or 0)
        _set_metadata(sidecar, "schema_version", ARCHIVE_API_VECTOR_INDEX_SCHEMA_VERSION)
        _set_metadata(sidecar, "embedding_provider", DEFAULT_EMBEDDING_PROVIDER)
        _set_metadata(sidecar, "embedding_model", clean_model)
        _set_metadata(sidecar, "vector_dim", str(vector_dim))
        _set_metadata(sidecar, "updated_at", indexed_at)
        _set_metadata(sidecar, "source", "api_embedding_sqlite_sidecar")
        sidecar.commit()
    finally:
        sidecar.close()
    _clear_api_vector_cache(path)

    return {
        "schema_version": ARCHIVE_API_VECTOR_INDEX_SCHEMA_VERSION,
        "status": "ok",
        "index_path": str(path),
        "embedding_provider": DEFAULT_EMBEDDING_PROVIDER,
        "embedding_model": clean_model,
        "vector_dim": vector_dim,
        "source_rows_scanned": len(rows),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "provider_calls": provider_calls,
        "prompt_tokens": prompt_tokens,
        "total_tokens": total_tokens,
        "provider_duration_ms": provider_duration_ms,
        "indexed_at": indexed_at,
        "privacy": _api_vector_privacy(sidecar_write=True),
    }


def search_archive_api_vector_index(
    *,
    index_path: str | Path,
    query: str,
    filters: ArchiveSearchFilters | Mapping[str, object] | None = None,
    limit: int = 10,
    max_scan_rows: int = DEFAULT_MAX_INDEX_ROWS,
    model: str | None = None,
    embedder: EmbeddingClient | None = None,
    require_approval: bool = True,
) -> list[ArchiveSearchResult]:
    if require_approval and not api_embeddings_approved():
        raise ArchiveApiVectorIndexError("API embeddings require PRM_API_EMBEDDINGS_APPROVED=1")
    clean_query = " ".join(str(query or "").split())
    if not clean_query:
        raise ArchiveApiVectorIndexError("query is required")
    path = Path(index_path)
    if not path.exists():
        raise ArchiveApiVectorIndexError("API vector index sidecar is missing")
    normalized_filters = _coerce_filters(filters)
    clean_limit = max(1, int(limit or 10))
    clean_scan = max(clean_limit, min(DEFAULT_MAX_INDEX_ROWS, int(max_scan_rows or DEFAULT_MAX_INDEX_ROWS)))
    active_model = _embedding_model(model)
    active_embedder = embedder or _openai_embed_texts

    sidecar = sqlite3.connect(path)
    try:
        sidecar.row_factory = sqlite3.Row
        _validate_index(sidecar, model=active_model)
        query_batch = active_embedder([clean_query], active_model)
        if len(query_batch.vectors) != 1:
            raise ArchiveApiVectorIndexError("embedding provider returned invalid query vector count")
        query_vector = _normalize_dense_vector(query_batch.vectors[0])
        row_bundle = _load_cached_candidate_rows(path, sidecar, normalized_filters, limit=clean_scan, model=active_model)
    finally:
        sidecar.close()
    if not query_vector:
        return []

    scored = _score_candidate_rows(query_vector, row_bundle, normalized_filters)
    scored.sort(
        key=lambda pair: (
            pair[0],
            str(pair[1]["posted_at"] or ""),
            int(pair[1]["post_id"] or 0),
        ),
        reverse=True,
    )
    return [_api_result_from_row(row, score=score) for score, row in scored[:clean_limit]]


def search_telegram_archive_api_hybrid(
    connection: sqlite3.Connection,
    query: str,
    *,
    api_vector_index_path: str | Path,
    filters: ArchiveSearchFilters | Mapping[str, object] | None = None,
    limit: int = 10,
    vector_policy: str = "always",
    model: str | None = None,
) -> list[ArchiveSearchResult]:
    clean_limit = max(1, int(limit or 10))
    clean_policy = str(vector_policy or "always").strip()
    if clean_policy not in {"fallback_on_fts_miss", "always"}:
        raise ArchiveApiVectorIndexError("vector_policy must be fallback_on_fts_miss or always")
    try:
        fts_results = search_telegram_archive(connection, query, filters=filters, limit=clean_limit)
    except Exception:
        fts_results = []
    if fts_results and clean_policy == "fallback_on_fts_miss":
        return _merge_fts_and_vector(fts_results, [], limit=clean_limit)
    try:
        vector_results = search_archive_api_vector_index(
            index_path=api_vector_index_path,
            query=query,
            filters=filters,
            limit=clean_limit,
            model=model,
        )
    except ArchiveApiVectorIndexError:
        vector_results = []
    return _merge_api_fts_and_vector(fts_results, vector_results, limit=clean_limit)


def api_embeddings_approved() -> bool:
    return os.environ.get("PRM_API_EMBEDDINGS_APPROVED", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "approved",
    }


def _embed_and_store(
    connection: sqlite3.Connection,
    pending: Sequence[tuple[Mapping[str, object], Any, Mapping[str, Any], str]],
    *,
    model: str,
    embedder: EmbeddingClient,
    indexed_at: str,
    existing: Mapping[str, tuple[str, str]],
) -> dict[str, int]:
    texts = [item[3] for item in pending]
    batch = embedder(texts, model)
    if len(batch.vectors) != len(pending):
        raise ArchiveApiVectorIndexError("embedding provider returned invalid vector count")
    inserted = updated = 0
    vector_dim = 0
    for (row_dict, document, metadata, _text), raw_vector in zip(pending, batch.vectors):
        vector = _normalize_dense_vector(raw_vector)
        if not vector:
            continue
        vector_dim = len(vector)
        connection.execute(
            """
            INSERT INTO archive_api_vector_documents (
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
                embedding_provider,
                embedding_model,
                vector_dim,
                vector_json,
                indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                embedding_provider=excluded.embedding_provider,
                embedding_model=excluded.embedding_model,
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
                batch.provider,
                batch.model or model,
                vector_dim,
                _dump_dense_vector(vector),
                indexed_at,
            ),
        )
        if document.archive_document_id in existing:
            updated += 1
        else:
            inserted += 1
    return {
        "inserted": inserted,
        "updated": updated,
        "prompt_tokens": int(batch.prompt_tokens or 0),
        "total_tokens": int(batch.total_tokens or 0),
        "duration_ms": int(batch.duration_ms or 0),
        "vector_dim": vector_dim,
    }


def _openai_embed_texts(texts: Sequence[str], model: str) -> ApiEmbeddingBatch:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ArchiveApiVectorIndexError("OPENAI_API_KEY is not set")
    endpoint = os.environ.get("OPENAI_EMBEDDINGS_URL", "").strip() or DEFAULT_OPENAI_EMBEDDINGS_URL
    payload = json.dumps({"model": model, "input": list(texts)}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PRMApiVectorIndexer/1.0",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(32 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise ArchiveApiVectorIndexError(f"embedding provider HTTP error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ArchiveApiVectorIndexError("embedding provider request failed") from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveApiVectorIndexError("embedding provider returned invalid JSON") from exc
    rows = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ArchiveApiVectorIndexError("embedding provider response missing data")
    ordered: list[list[float] | None] = [None] * len(texts)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        embedding = row.get("embedding")
        if 0 <= index < len(ordered) and isinstance(embedding, list):
            ordered[index] = [float(value) for value in embedding]
    if any(vector is None for vector in ordered):
        raise ArchiveApiVectorIndexError("embedding provider response missing vectors")
    usage = data.get("usage") if isinstance(data, Mapping) else {}
    usage = usage if isinstance(usage, Mapping) else {}
    return ApiEmbeddingBatch(
        vectors=[vector for vector in ordered if vector is not None],
        model=str(data.get("model") or model),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        duration_ms=duration_ms,
        provider=DEFAULT_EMBEDDING_PROVIDER,
    )


def _ensure_index_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS archive_api_vector_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS archive_api_vector_documents (
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
            embedding_provider TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            vector_dim INTEGER NOT NULL,
            vector_json TEXT NOT NULL CHECK(json_valid(vector_json)),
            indexed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_archive_api_vector_channel
            ON archive_api_vector_documents(channel_username);
        CREATE INDEX IF NOT EXISTS idx_archive_api_vector_posted
            ON archive_api_vector_documents(posted_at);
        CREATE INDEX IF NOT EXISTS idx_archive_api_vector_model
            ON archive_api_vector_documents(embedding_model);
        """
    )


def _metadata(connection: sqlite3.Connection, key: str) -> str:
    if not _table_exists(connection, "archive_api_vector_metadata"):
        return ""
    row = connection.execute(
        "SELECT value FROM archive_api_vector_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row[0] if row else "")


def _set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO archive_api_vector_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _validate_index(connection: sqlite3.Connection, *, model: str) -> None:
    if not _table_exists(connection, "archive_api_vector_documents"):
        raise ArchiveApiVectorIndexError("API vector index table is missing")
    if _metadata(connection, "schema_version") != ARCHIVE_API_VECTOR_INDEX_SCHEMA_VERSION:
        raise ArchiveApiVectorIndexError("API vector index schema_version is invalid")
    if _metadata(connection, "embedding_provider") != DEFAULT_EMBEDDING_PROVIDER:
        raise ArchiveApiVectorIndexError("API vector index embedding_provider is invalid")
    if _metadata(connection, "embedding_model") != model:
        raise ArchiveApiVectorIndexError("API vector index embedding_model is invalid")


def _load_cached_candidate_rows(
    path: Path,
    connection: sqlite3.Connection,
    filters: ArchiveSearchFilters,
    *,
    limit: int,
    model: str,
) -> list[tuple[dict[str, Any], list[float]]]:
    cache_key = _api_vector_cache_key(path, model)
    cached = _API_VECTOR_ROW_CACHE.get(cache_key)
    if cached is None:
        rows = connection.execute(
            """
            SELECT *
            FROM archive_api_vector_documents
            WHERE embedding_model = ?
            ORDER BY posted_at DESC, post_id DESC
            LIMIT ?
            """,
            (model, DEFAULT_MAX_INDEX_ROWS),
        ).fetchall()
        row_dicts = [{key: row[key] for key in row.keys()} for row in rows]
        vectors = [_load_dense_vector(str(row["vector_json"] or "")) for row in rows]
        matrix = None
        if np is not None and vectors:
            try:
                matrix = np.asarray(vectors, dtype="float32")
            except Exception:
                matrix = None
        cached = {"rows": row_dicts, "vectors": vectors, "matrix": matrix}
        _API_VECTOR_ROW_CACHE.clear()
        _API_VECTOR_ROW_CACHE[cache_key] = cached
    selected_rows: list[dict[str, Any]] = []
    selected_vectors: list[list[float]] = []
    selected_indexes: list[int] = []
    rows = list(cached.get("rows") or [])
    vectors = list(cached.get("vectors") or [])
    for index, (row, vector) in enumerate(zip(rows, vectors)):
        if not _row_matches_primary_filters(row, filters):
            continue
        selected_rows.append(row)
        selected_vectors.append(vector)
        selected_indexes.append(index)
        if len(selected_rows) >= limit:
            break
    matrix = cached.get("matrix")
    selected_matrix = None
    if np is not None and matrix is not None and selected_indexes:
        selected_matrix = matrix[selected_indexes]
    return {"rows": selected_rows, "vectors": selected_vectors, "matrix": selected_matrix}


def _score_candidate_rows(
    query_vector: Sequence[float],
    row_bundle: Mapping[str, Any],
    filters: ArchiveSearchFilters,
) -> list[tuple[float, Mapping[str, Any]]]:
    rows = list(row_bundle.get("rows") or [])
    if not rows:
        return []
    matrix = row_bundle.get("matrix")
    if np is not None and matrix is not None:
        query = np.asarray(query_vector, dtype="float32")
        scores = matrix @ query
        return [
            (float(scores[index]), row)
            for index, row in enumerate(rows)
            if _row_matches_filters(row, filters)
        ]
    vectors = list(row_bundle.get("vectors") or [])
    scored: list[tuple[float, Mapping[str, Any]]] = []
    for row, vector in zip(rows, vectors):
        if not _row_matches_filters(row, filters):
            continue
        scored.append((_dot_dense(query_vector, vector), row))
    return scored


def _api_result_from_row(row: Mapping[str, Any], *, score: float) -> ArchiveSearchResult:
    result = _result_from_vector_row(row, score=score)
    return replace(result, retrieval_mode="api_vector_archive", semantic_score=round(float(score), 6))


def _merge_api_fts_and_vector(
    fts_results: Sequence[ArchiveSearchResult],
    vector_results: Sequence[ArchiveSearchResult],
    *,
    limit: int,
) -> list[ArchiveSearchResult]:
    merged = _merge_fts_and_vector(fts_results, vector_results, limit=limit)
    result: list[ArchiveSearchResult] = []
    for item in merged:
        mode = item.retrieval_mode
        if mode == "hybrid_vector_only":
            mode = "api_hybrid_vector_only"
        elif mode == "hybrid_fts_vector":
            mode = "api_hybrid_fts_vector"
        elif mode == "hybrid_fts_only":
            mode = "api_hybrid_fts_only"
        result.append(replace(item, retrieval_mode=mode))
    return result


def _normalize_dense_vector(raw: Sequence[object]) -> list[float]:
    vector: list[float] = []
    for value in raw:
        try:
            vector.append(float(value))
        except (TypeError, ValueError):
            return []
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return []
    return [value / norm for value in vector]


def _dump_dense_vector(vector: Sequence[float]) -> str:
    return json.dumps([round(float(value), 8) for value in vector], separators=(",", ":"))


def _load_dense_vector(raw: str) -> list[float]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    try:
        return [float(value) for value in data]
    except (TypeError, ValueError):
        return []


def _dot_dense(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _delete_stale_api(connection: sqlite3.Connection, live_ids: set[str]) -> int:
    rows = connection.execute("SELECT archive_document_id FROM archive_api_vector_documents").fetchall()
    stale = [str(row[0]) for row in rows if str(row[0]) not in live_ids]
    if stale:
        connection.executemany(
            "DELETE FROM archive_api_vector_documents WHERE archive_document_id = ?",
            [(archive_document_id,) for archive_document_id in stale],
        )
    return len(stale)


def _api_vector_cache_key(path: Path, model: str) -> tuple[str, int, int, str]:
    stat = path.stat()
    return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size), model)


def _clear_api_vector_cache(path: Path) -> None:
    resolved = str(path.resolve())
    for key in list(_API_VECTOR_ROW_CACHE):
        if key[0] == resolved:
            _API_VECTOR_ROW_CACHE.pop(key, None)


def _embedding_model(value: str | None = None) -> str:
    clean = str(value or "").strip() or os.environ.get("PRM_EMBEDDING_MODEL", "").strip()
    return clean or DEFAULT_EMBEDDING_MODEL


def _api_vector_privacy(*, sidecar_write: bool) -> dict[str, bool | str]:
    return {
        "embedding_provider": DEFAULT_EMBEDDING_PROVIDER,
        "provider_egress": True,
        "external_embedding_provider_egress": True,
        "bounded_telegram_text_provider_egress": True,
        "raw_telegram_corpus_egress": False,
        "provider_payload_recorded": False,
        "canonical_db_mutated": False,
        "sidecar_write": bool(sidecar_write),
    }
