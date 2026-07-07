import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from config.settings import CHEAP_MODEL, Settings
from db.knowledge_atoms import (
    ATOM_TYPES,
    STALENESS_STATUSES,
    build_atom_key,
    complete_knowledge_extraction_batch,
    fetch_knowledge_extraction_batches,
    record_knowledge_atom,
    record_knowledge_extraction_batch,
)
from llm.client import complete


LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "knowledge-atoms-v1"
DEFAULT_BATCH_SIZE = 12
MAX_POST_TEXT_CHARS = 1400
MAX_ATOMS_PER_BATCH = 6
KNOWLEDGE_EXTRACTION_MAX_TOKENS = 4096
KNOWLEDGE_EXTRACTION_ATTEMPTS = 2


class KnowledgeExtractionError(Exception):
    pass


class KnowledgeExtractionValidationError(KnowledgeExtractionError):
    pass


@dataclass(frozen=True)
class SourcePost:
    post_id: int
    raw_post_id: int
    channel_username: str
    message_id: int | None
    posted_at: str
    content: str
    message_url: str


@dataclass(frozen=True)
class ExtractionSummary:
    week_labels: tuple[str, ...]
    model: str
    prompt_version: str
    posts_seen: int
    batches_total: int
    batches_completed: int
    batches_skipped: int
    atoms_recorded: int
    errors: tuple[str, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _week_label_for(value: datetime) -> str:
    current = value.astimezone(timezone.utc)
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _week_start(week_label: str) -> datetime:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    week_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    return datetime.combine(week_date, datetime.min.time(), tzinfo=timezone.utc)


def _week_bounds(week_label: str) -> tuple[str, str]:
    start = _week_start(week_label)
    end = start + timedelta(days=7)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def week_labels_for_lookback(weeks: int, *, now: datetime | None = None) -> tuple[str, ...]:
    current = now or _utc_now()
    current_start = _week_start(_week_label_for(current))
    count = max(1, int(weeks or 1))
    labels: list[str] = []
    for offset in range(count - 1, -1, -1):
        labels.append(_week_label_for(current_start - timedelta(days=7 * offset)))
    return tuple(labels)


def resolve_extraction_model(model: str | None) -> str:
    selected = str(model or "cheap").strip()
    if selected == "cheap":
        return CHEAP_MODEL
    return selected


def _telegram_url(channel_username: str, message_id: int | None) -> str:
    channel = str(channel_username or "").strip().lstrip("@")
    if not channel or not message_id:
        return ""
    return f"https://t.me/{channel}/{message_id}"


def _load_week_posts(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    limit: int | None = None,
) -> list[SourcePost]:
    start_iso, end_iso = _week_bounds(week_label)
    limit_sql = "LIMIT ?" if limit and limit > 0 else ""
    params: list[object] = [start_iso, end_iso]
    if limit and limit > 0:
        params.append(int(limit))
    rows = connection.execute(
        f"""
        SELECT
            posts.id AS post_id,
            posts.raw_post_id,
            posts.channel_username,
            posts.posted_at,
            posts.content,
            raw_posts.message_id,
            raw_posts.message_url
        FROM posts
        LEFT JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE posts.posted_at >= ?
          AND posts.posted_at < ?
          AND length(trim(posts.content)) > 0
        ORDER BY posts.channel_username ASC, posts.posted_at ASC, posts.id ASC
        {limit_sql}
        """,
        params,
    ).fetchall()
    posts: list[SourcePost] = []
    for row in rows:
        message_id = row["message_id"]
        fallback_url = _telegram_url(str(row["channel_username"] or ""), int(message_id) if message_id else None)
        posts.append(
            SourcePost(
                post_id=int(row["post_id"]),
                raw_post_id=int(row["raw_post_id"]),
                channel_username=str(row["channel_username"] or ""),
                message_id=int(message_id) if message_id is not None else None,
                posted_at=str(row["posted_at"] or ""),
                content=str(row["content"] or ""),
                message_url=str(row["message_url"] or fallback_url or ""),
            )
        )
    return posts


def _chunked(values: list[SourcePost], size: int) -> Iterable[list[SourcePost]]:
    chunk_size = max(1, int(size or DEFAULT_BATCH_SIZE))
    for index in range(0, len(values), chunk_size):
        yield values[index:index + chunk_size]


def _group_by_channel(posts: list[SourcePost]) -> list[tuple[str, list[SourcePost]]]:
    groups: list[tuple[str, list[SourcePost]]] = []
    current_channel: str | None = None
    current_posts: list[SourcePost] = []
    for post in posts:
        channel = post.channel_username or "unknown"
        if current_channel is None:
            current_channel = channel
        if channel != current_channel:
            groups.append((current_channel, current_posts))
            current_channel = channel
            current_posts = []
        current_posts.append(post)
    if current_channel is not None:
        groups.append((current_channel, current_posts))
    return groups


def _batch_key(
    *,
    week_label: str,
    channel_username: str,
    model: str,
    prompt_version: str,
    source_post_ids: list[int],
) -> str:
    payload = {
        "week_label": week_label,
        "channel_username": channel_username,
        "model": model,
        "prompt_version": prompt_version,
        "source_post_ids": source_post_ids,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"knowledge-extract:{digest}"


def _post_payload(post: SourcePost) -> dict:
    return {
        "post_id": post.post_id,
        "channel": post.channel_username,
        "posted_at": post.posted_at,
        "message_url": post.message_url,
        "text": post.content[:MAX_POST_TEXT_CHARS],
    }


def _build_prompt(week_label: str, posts: list[SourcePost], *, retry_error: str | None = None) -> str:
    atom_types = ", ".join(sorted(ATOM_TYPES))
    payload = [_post_payload(post) for post in posts]
    retry_instruction = ""
    if retry_error:
        retry_instruction = (
            "\nPrevious output failed validation. Return a smaller valid JSON object now. "
            f"Validation error: {retry_error}\n"
        )
    return (
        "Extract compact AI knowledge atoms from these Telegram posts.\n"
        "Return JSON only, with this shape:\n"
        "{\"atoms\":[{\"atom_type\":\"engineering_practice\",\"claim\":\"short claim\","
        "\"summary\":\"one sentence\",\"evidence_quote\":\"short exact excerpt\","
        "\"source_post_ids\":[123],\"source_urls\":[\"https://t.me/channel/123\"],"
        "\"entities\":[\"entity\"],\"tools\":[],\"models\":[],\"practices\":[],"
        "\"confidence\":0.0,\"novelty_score\":0.0,\"practical_utility_score\":0.0,"
        "\"frontier_relevance_score\":0.0,\"operator_relevance_score\":0.0,"
        "\"staleness_status\":\"active\",\"why_it_matters\":\"why this matters\"}]}\n"
        f"Allowed atom_type values: {atom_types}.\n"
        f"Return at most {MAX_ATOMS_PER_BATCH} atoms total. Use fewer atoms when evidence is weak.\n"
        "Keep every string concise: claim, summary, evidence_quote, and why_it_matters must each stay under 180 characters.\n"
        "Do not use markdown, comments, trailing commas, or extra keys. The response must be one complete JSON object.\n"
        "Only cite post_id values from the provided posts. Prefer no atom over weak or generic claims.\n"
        f"{retry_instruction}"
        f"Week: {week_label}\n"
        f"Posts JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _parse_json_object(raw_text: str) -> dict:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KnowledgeExtractionValidationError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise KnowledgeExtractionValidationError("LLM JSON root must be an object")
    return parsed


def _as_list(value: object, field_name: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise KnowledgeExtractionValidationError(f"{field_name} must be a list")
    return value


def _score(value: object, field_name: str) -> float:
    try:
        score = float(value if value is not None else 0.0)
    except (TypeError, ValueError) as exc:
        raise KnowledgeExtractionValidationError(f"{field_name} must be a number") from exc
    if score < 0.0 or score > 1.0:
        raise KnowledgeExtractionValidationError(f"{field_name} must be between 0 and 1")
    return score


def _validate_atoms_payload(payload: dict, posts: list[SourcePost]) -> list[dict]:
    atoms = payload.get("atoms")
    if not isinstance(atoms, list):
        raise KnowledgeExtractionValidationError("LLM JSON must contain atoms list")
    posts_by_id = {post.post_id: post for post in posts}
    normalized_atoms: list[dict] = []
    for index, raw_atom in enumerate(atoms, start=1):
        if not isinstance(raw_atom, dict):
            raise KnowledgeExtractionValidationError(f"atom #{index} must be an object")
        atom_type = str(raw_atom.get("atom_type") or "").strip()
        if atom_type not in ATOM_TYPES:
            raise KnowledgeExtractionValidationError(f"atom #{index} has unsupported atom_type={atom_type!r}")
        claim = str(raw_atom.get("claim") or "").strip()
        evidence_quote = str(raw_atom.get("evidence_quote") or "").strip()
        if not claim:
            raise KnowledgeExtractionValidationError(f"atom #{index} claim is required")
        if not evidence_quote:
            raise KnowledgeExtractionValidationError(f"atom #{index} evidence_quote is required")
        source_post_ids = []
        for value in _as_list(raw_atom.get("source_post_ids"), f"atom #{index} source_post_ids"):
            try:
                post_id = int(value)
            except (TypeError, ValueError) as exc:
                raise KnowledgeExtractionValidationError(f"atom #{index} source_post_ids must be integers") from exc
            if post_id not in posts_by_id:
                raise KnowledgeExtractionValidationError(f"atom #{index} cites unknown post_id={post_id}")
            source_post_ids.append(post_id)
        if not source_post_ids:
            raise KnowledgeExtractionValidationError(f"atom #{index} must cite at least one source_post_id")
        source_urls = [
            str(url).strip()
            for url in _as_list(raw_atom.get("source_urls"), f"atom #{index} source_urls")
            if str(url).strip()
        ]
        if not source_urls:
            source_urls = [posts_by_id[post_id].message_url for post_id in source_post_ids if posts_by_id[post_id].message_url]
        if not source_urls:
            raise KnowledgeExtractionValidationError(f"atom #{index} must cite at least one source URL")
        staleness_status = str(raw_atom.get("staleness_status") or "active").strip() or "active"
        if staleness_status not in STALENESS_STATUSES:
            raise KnowledgeExtractionValidationError(
                f"atom #{index} has unsupported staleness_status={staleness_status!r}"
            )
        normalized_atoms.append(
            {
                "atom_type": atom_type,
                "claim": claim,
                "summary": str(raw_atom.get("summary") or "").strip(),
                "evidence_quote": evidence_quote,
                "source_post_ids": source_post_ids,
                "source_urls": source_urls,
                "entities": [str(item).strip() for item in _as_list(raw_atom.get("entities"), "entities") if str(item).strip()],
                "tools": [str(item).strip() for item in _as_list(raw_atom.get("tools"), "tools") if str(item).strip()],
                "models": [str(item).strip() for item in _as_list(raw_atom.get("models"), "models") if str(item).strip()],
                "practices": [str(item).strip() for item in _as_list(raw_atom.get("practices"), "practices") if str(item).strip()],
                "confidence": _score(raw_atom.get("confidence"), "confidence"),
                "novelty_score": _score(raw_atom.get("novelty_score"), "novelty_score"),
                "practical_utility_score": _score(raw_atom.get("practical_utility_score"), "practical_utility_score"),
                "frontier_relevance_score": _score(raw_atom.get("frontier_relevance_score"), "frontier_relevance_score"),
                "operator_relevance_score": _score(raw_atom.get("operator_relevance_score"), "operator_relevance_score"),
                "staleness_status": staleness_status,
                "why_it_matters": str(raw_atom.get("why_it_matters") or "").strip(),
            }
        )
    return normalized_atoms


def _extract_atoms_from_batch(
    *,
    week_label: str,
    posts: list[SourcePost],
    model: str,
) -> list[dict]:
    last_error: KnowledgeExtractionValidationError | None = None
    for attempt in range(1, KNOWLEDGE_EXTRACTION_ATTEMPTS + 1):
        prompt = _build_prompt(week_label, posts, retry_error=str(last_error) if last_error else None)
        raw = complete(
            prompt=prompt,
            system="You extract source-grounded structured JSON. Return JSON only.",
            max_tokens=KNOWLEDGE_EXTRACTION_MAX_TOKENS,
            category="knowledge_extraction",
            model=model,
        )
        try:
            return _validate_atoms_payload(_parse_json_object(raw), posts)
        except KnowledgeExtractionValidationError as exc:
            last_error = exc
            if attempt < KNOWLEDGE_EXTRACTION_ATTEMPTS:
                LOGGER.warning(
                    "Knowledge extraction validation retry week=%s posts=%d attempt=%d/%d error=%s",
                    week_label,
                    len(posts),
                    attempt,
                    KNOWLEDGE_EXTRACTION_ATTEMPTS,
                    exc,
                )
                continue
            raise

    raise last_error or KnowledgeExtractionValidationError("knowledge extraction validation failed")


def _is_low_credit_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        message = str(current).lower()
        if "credit balance is too low" in message or "purchase credits" in message:
            return True
        current = current.__cause__
    return False


def run_knowledge_extraction(
    settings: Settings,
    *,
    weeks: int,
    model: str = "cheap",
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    force: bool = False,
) -> ExtractionSummary:
    resolved_model = resolve_extraction_model(model)
    week_labels = week_labels_for_lookback(weeks)
    posts_seen = 0
    batches_total = 0
    batches_completed = 0
    batches_skipped = 0
    atoms_recorded = 0
    errors: list[str] = []

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        for week_label in week_labels:
            week_posts = _load_week_posts(connection, week_label, limit=limit)
            posts_seen += len(week_posts)
            for channel_username, channel_posts in _group_by_channel(week_posts):
                for post_batch in _chunked(channel_posts, batch_size):
                    source_post_ids = [post.post_id for post in post_batch]
                    key = _batch_key(
                        week_label=week_label,
                        channel_username=channel_username,
                        model=resolved_model,
                        prompt_version=PROMPT_VERSION,
                        source_post_ids=source_post_ids,
                    )
                    existing = fetch_knowledge_extraction_batches(connection, batch_key=key, limit=1)
                    if existing and existing[0]["status"] == "completed" and not force:
                        batches_skipped += 1
                        continue
                    batches_total += 1
                    batch = record_knowledge_extraction_batch(
                        connection,
                        batch_key=key,
                        week_label=week_label,
                        channel_username=channel_username,
                        post_count=len(post_batch),
                        model=resolved_model,
                        prompt_version=PROMPT_VERSION,
                        status="running",
                    )
                    try:
                        atoms = _extract_atoms_from_batch(
                            week_label=week_label,
                            posts=post_batch,
                            model=resolved_model,
                        )
                        for atom in atoms:
                            atom_key = build_atom_key(
                                atom_type=atom["atom_type"],
                                claim=atom["claim"],
                                source_post_ids=atom["source_post_ids"],
                            )
                            record_knowledge_atom(
                                connection,
                                atom_key=atom_key,
                                extraction_batch_id=batch["id"],
                                week_label=week_label,
                                first_seen_at=min(post.posted_at for post in post_batch),
                                last_seen_at=max(post.posted_at for post in post_batch),
                                **atom,
                            )
                            atoms_recorded += 1
                        complete_knowledge_extraction_batch(connection, batch_id=batch["id"], status="completed")
                        batches_completed += 1
                    except Exception as exc:
                        error = f"week={week_label} channel={channel_username} batch={key}: {exc}"
                        LOGGER.warning("Knowledge extraction batch failed %s", error, exc_info=True)
                        complete_knowledge_extraction_batch(
                            connection,
                            batch_id=batch["id"],
                            status="failed",
                            error=str(exc),
                        )
                        errors.append(error)
                        if _is_low_credit_error(exc):
                            LOGGER.error("Stopping knowledge extraction after non-retryable provider credit error")
                            return ExtractionSummary(
                                week_labels=week_labels,
                                model=resolved_model,
                                prompt_version=PROMPT_VERSION,
                                posts_seen=posts_seen,
                                batches_total=batches_total,
                                batches_completed=batches_completed,
                                batches_skipped=batches_skipped,
                                atoms_recorded=atoms_recorded,
                                errors=tuple(errors),
                            )

    return ExtractionSummary(
        week_labels=week_labels,
        model=resolved_model,
        prompt_version=PROMPT_VERSION,
        posts_seen=posts_seen,
        batches_total=batches_total,
        batches_completed=batches_completed,
        batches_skipped=batches_skipped,
        atoms_recorded=atoms_recorded,
        errors=tuple(errors),
    )


def format_knowledge_extraction_summary(summary: ExtractionSummary) -> str:
    lines = [
        "Knowledge extraction summary",
        f"weeks={','.join(summary.week_labels)} model={summary.model} prompt_version={summary.prompt_version}",
        (
            "counts: "
            f"posts_seen={summary.posts_seen} "
            f"batches_total={summary.batches_total} "
            f"batches_completed={summary.batches_completed} "
            f"batches_skipped={summary.batches_skipped} "
            f"atoms_recorded={summary.atoms_recorded} "
            f"errors={len(summary.errors)}"
        ),
    ]
    if summary.errors:
        lines.append("errors:")
        lines.extend(f"  - {error}" for error in summary.errors[:10])
    return "\n".join(lines).rstrip() + "\n"
