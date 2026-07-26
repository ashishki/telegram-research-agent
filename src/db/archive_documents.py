import hashlib
import re
from dataclasses import dataclass, replace
from typing import Mapping, Sequence


DEFAULT_CHUNK_MAX_CHARS = 3200
CONTENT_HASH_ALGORITHM = "sha256:v1:ws-casefold"

_WHITESPACE_RE = re.compile(r"\s+")


class ArchiveDocumentError(ValueError):
    """Raised when a row cannot be mapped to a stable archive document."""


@dataclass(frozen=True)
class ArchiveDocument:
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
    content_hash: str
    content_hash_algorithm: str
    chunk_content_hash: str
    duplicate_cluster_id: str | None
    repost_cluster_id: str | None
    chunk_index: int | None
    chunk_count: int
    chunk_start_char: int
    chunk_end_char: int
    content: str


@dataclass(frozen=True)
class ArchiveDocumentExclusion:
    post_id: int | None
    raw_post_id: int | None
    archive_document_id: str | None
    reason: str


@dataclass(frozen=True)
class ArchiveBuildResult:
    documents: tuple[ArchiveDocument, ...]
    exclusions: tuple[ArchiveDocumentExclusion, ...]


def archive_post_document_id(*, channel_id: int, message_id: int) -> str:
    """Stable post-level identity independent of local SQLite row ids."""
    return f"tg:{int(channel_id)}:{int(message_id)}"


def archive_chunk_document_id(post_document_id: str, *, chunk_index: int, chunk_count: int) -> str:
    if chunk_count <= 1:
        return post_document_id
    return f"{post_document_id}:chunk:{chunk_index:04d}"


def canonicalize_content_for_hash(content: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(content or "").strip()).casefold()


def content_hash(content: str) -> str:
    canonical = canonicalize_content_for_hash(content)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_archive_documents(
    rows: Sequence[Mapping[str, object]],
    *,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    assign_duplicate_clusters: bool = True,
) -> ArchiveBuildResult:
    documents: list[ArchiveDocument] = []
    exclusions: list[ArchiveDocumentExclusion] = []

    for row in rows:
        row_documents, row_exclusion = archive_documents_for_row(
            row,
            chunk_max_chars=chunk_max_chars,
        )
        documents.extend(row_documents)
        if row_exclusion is not None:
            exclusions.append(row_exclusion)

    if assign_duplicate_clusters:
        documents = _with_duplicate_clusters(documents)

    return ArchiveBuildResult(
        documents=tuple(documents),
        exclusions=tuple(exclusions),
    )


def archive_documents_for_row(
    row: Mapping[str, object],
    *,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> tuple[tuple[ArchiveDocument, ...], ArchiveDocumentExclusion | None]:
    if chunk_max_chars <= 0:
        raise ArchiveDocumentError("chunk_max_chars must be positive")

    post_id = _optional_int(row, "post_id", "id")
    raw_post_id = _optional_int(row, "raw_post_id")
    channel_id = _required_int(row, "channel_id")
    message_id = _required_int(row, "message_id")
    post_document_id = archive_post_document_id(
        channel_id=channel_id,
        message_id=message_id,
    )

    body = str(_value(row, "content", default="") or "").strip()
    if not body:
        return (
            (),
            ArchiveDocumentExclusion(
                post_id=post_id,
                raw_post_id=raw_post_id,
                archive_document_id=post_document_id,
                reason="empty_canonical_body",
            ),
        )

    resolved_post_id = _require_present_int(post_id, "post_id")
    resolved_raw_post_id = _require_present_int(raw_post_id, "raw_post_id")
    channel_username = str(_required_value(row, "channel_username")).strip()
    posted_at = str(_required_value(row, "posted_at")).strip()
    language = str(_value(row, "language_detected", "language", default="unknown") or "unknown").strip()
    source_url = _source_url(
        channel_username=channel_username,
        message_id=message_id,
        message_url=str(_value(row, "message_url", "source_url", default="") or ""),
    )
    post_content_hash = content_hash(body)
    spans = _chunk_spans(body, max_chars=chunk_max_chars)
    chunk_count = len(spans)
    repost_cluster_id = _repost_cluster_id(str(_value(row, "forward_from", default="") or ""))

    documents: list[ArchiveDocument] = []
    for chunk_index, (start, end) in enumerate(spans):
        chunk_text = body[start:end].strip()
        document_chunk_index = chunk_index if chunk_count > 1 else None
        archive_document_id = archive_chunk_document_id(
            post_document_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
        )
        documents.append(
            ArchiveDocument(
                archive_document_id=archive_document_id,
                post_archive_document_id=post_document_id,
                post_id=resolved_post_id,
                raw_post_id=resolved_raw_post_id,
                channel_username=channel_username,
                channel_id=channel_id,
                message_id=message_id,
                posted_at=posted_at,
                source_url=source_url,
                language=language or "unknown",
                content_hash=post_content_hash,
                content_hash_algorithm=CONTENT_HASH_ALGORITHM,
                chunk_content_hash=content_hash(chunk_text),
                duplicate_cluster_id=None,
                repost_cluster_id=repost_cluster_id,
                chunk_index=document_chunk_index,
                chunk_count=chunk_count,
                chunk_start_char=start,
                chunk_end_char=end,
                content=chunk_text,
            )
        )

    return tuple(documents), None


def _with_duplicate_clusters(documents: list[ArchiveDocument]) -> list[ArchiveDocument]:
    posts_by_hash: dict[str, set[str]] = {}
    for document in documents:
        posts_by_hash.setdefault(document.content_hash, set()).add(document.post_archive_document_id)

    duplicate_hashes = {
        digest
        for digest, post_ids in posts_by_hash.items()
        if len(post_ids) > 1
    }
    if not duplicate_hashes:
        return documents

    updated: list[ArchiveDocument] = []
    for document in documents:
        if document.content_hash in duplicate_hashes:
            updated.append(
                replace(
                    document,
                    duplicate_cluster_id=f"exact:{document.content_hash}",
                )
            )
        else:
            updated.append(document)
    return updated


def _chunk_spans(content: str, *, max_chars: int) -> tuple[tuple[int, int], ...]:
    if len(content) <= max_chars:
        return ((0, len(content)),)

    spans: list[tuple[int, int]] = []
    start = 0
    content_length = len(content)
    while start < content_length:
        hard_end = min(start + max_chars, content_length)
        if hard_end == content_length:
            end = hard_end
        else:
            paragraph_split = content.rfind("\n\n", start, hard_end)
            newline_split = content.rfind("\n", start, hard_end)
            space_split = content.rfind(" ", start, hard_end)
            split_at = max(paragraph_split, newline_split, space_split)
            if split_at <= start:
                end = hard_end
            else:
                end = split_at

        while start < end and content[start].isspace():
            start += 1
        while end > start and content[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))

        next_start = end
        while next_start < content_length and content[next_start].isspace():
            next_start += 1
        if next_start <= start:
            next_start = hard_end
        start = next_start

    return tuple(spans) or ((0, len(content)),)


def _source_url(*, channel_username: str, message_id: int, message_url: str) -> str:
    value = message_url.strip()
    if value:
        return value
    channel = channel_username.strip().lstrip("@")
    if not channel:
        raise ArchiveDocumentError("channel_username is required to build source_url")
    return f"https://t.me/{channel}/{int(message_id)}"


def _repost_cluster_id(forward_from: str) -> str | None:
    canonical = str(forward_from or "").strip()
    if not canonical:
        return None
    digest = hashlib.sha256(canonicalize_content_for_hash(canonical).encode("utf-8")).hexdigest()
    return f"forward:{digest[:16]}"


def _required_value(row: Mapping[str, object], *keys: str) -> object:
    value = _value(row, *keys, default=None)
    if value is None or str(value).strip() == "":
        joined = "/".join(keys)
        raise ArchiveDocumentError(f"{joined} is required")
    return value


def _value(row: Mapping[str, object], *keys: str, default: object = None) -> object:
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()
    for key in keys:
        if key in row_keys:
            return row[key]
    return default


def _required_int(row: Mapping[str, object], *keys: str) -> int:
    return _require_present_int(_optional_int(row, *keys), "/".join(keys))


def _optional_int(row: Mapping[str, object], *keys: str) -> int | None:
    value = _value(row, *keys, default=None)
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        joined = "/".join(keys)
        raise ArchiveDocumentError(f"{joined} must be an integer") from exc


def _require_present_int(value: int | None, label: str) -> int:
    if value is None:
        raise ArchiveDocumentError(f"{label} is required")
    return value
