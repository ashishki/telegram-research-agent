from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable

from config.settings import PROJECT_ROOT


SOURCE_PACKET_SCHEMA_VERSION = "ai_transformation_source_packet.v1"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output" / "ai_transformation_source_packets"


@dataclass(frozen=True)
class TelegramPost:
    channel_username: str
    message_id: int
    posted_at: str
    source_url: str
    text: str
    views: int | None = None
    reactions: int | None = None
    source: str = "telegram_public_preview"

    def key(self) -> tuple[str, int]:
        return (_normalize_channel_username(self.channel_username), int(self.message_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_username": _normalize_channel_username(self.channel_username),
            "message_id": int(self.message_id),
            "posted_at": self.posted_at,
            "source_url": self.source_url,
            "text": self.text,
            "views": self.views,
            "reactions": self.reactions,
            "source": self.source,
        }


LiveFetcher = Callable[..., list[TelegramPost]]


def build_ai_transformation_source_packet(
    *,
    db_path: str | Path,
    days: int = 92,
    top_channels: int = 8,
    max_live_pages: int = 8,
    fetch_live: bool = False,
    output_root: str | Path | None = None,
    now: datetime | None = None,
    max_posts_in_markdown: int = 120,
    live_fetcher: LiveFetcher | None = None,
) -> dict[str, Any]:
    generated_at = _as_utc(now or datetime.now(timezone.utc))
    window_days = max(1, int(days or 92))
    window_start = generated_at - timedelta(days=window_days)
    output_dir = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT

    db = Path(db_path)
    with _connect_readonly(db) as connection:
        channels = _top_reaction_channels(connection, limit=max(1, int(top_channels or 8)))
        local_posts = _load_local_archive_posts(connection, channels=channels, window_start=window_start)

    live_posts: list[TelegramPost] = []
    live_status: dict[str, dict[str, Any]] = {}
    if fetch_live:
        active_fetcher = live_fetcher or fetch_telegram_preview_posts
        for channel in channels:
            normalized = _normalize_channel_username(channel["channel_username"])
            try:
                fetched = active_fetcher(
                    normalized,
                    window_start=window_start,
                    max_pages=max(1, int(max_live_pages or 8)),
                )
            except Exception as exc:
                live_status[normalized] = {
                    "status": "error",
                    "error": str(exc),
                    "posts_fetched": 0,
                }
                continue
            live_posts.extend(fetched)
            live_status[normalized] = {
                "status": "ok",
                "posts_fetched": len(fetched),
            }

    merged_posts = _merge_posts(local_posts=local_posts, live_posts=live_posts)
    relevant_posts = _rank_relevant_posts(merged_posts, window_start=window_start)
    channel_summary = _channel_summary(
        channels=channels,
        local_posts=local_posts,
        live_posts=live_posts,
        relevant_posts=relevant_posts,
        live_status=live_status,
    )
    bucket_summary = _bucket_summary(relevant_posts)
    payload: dict[str, Any] = {
        "schema_version": SOURCE_PACKET_SCHEMA_VERSION,
        "status": "ok" if channels else "no_reaction_channels",
        "generated_at": _iso_z(generated_at),
        "topic": "ai_transformation_companies",
        "generation_mode": "deterministic_private_source_packet",
        "window": {
            "days": window_days,
            "start": _iso_z(window_start),
            "end": _iso_z(generated_at),
        },
        "inputs": {
            "top_reaction_channels": channels,
            "fetch_live_public_telegram_preview": bool(fetch_live),
            "max_live_pages_per_channel": max(1, int(max_live_pages or 8)),
            "local_archive_read_mode": "sqlite_read_only",
        },
        "privacy": {
            "production_db_write": False,
            "migration": False,
            "telegram_service_start": False,
            "telegram_session_used": False,
            "provider_egress": False,
            "embeddings_or_vector_backend": False,
            "committable": False,
        },
        "source_counts": {
            "local_archive_posts": len(local_posts),
            "live_preview_posts": len(live_posts),
            "merged_posts": len(merged_posts),
            "relevant_posts": len(relevant_posts),
        },
        "channels": channel_summary,
        "bucket_summary": bucket_summary,
        "company_mentions": _company_mentions_summary(relevant_posts),
        "posts": [_post_card(post) for post in relevant_posts],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"ai_transformation_source_packet_{stamp}.json"
    md_path = output_dir / f"ai_transformation_source_packet_{stamp}.md"
    payload["outputs"] = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(
        render_ai_transformation_source_packet_markdown(
            payload,
            max_posts=max(1, int(max_posts_in_markdown or 120)),
        ),
        encoding="utf-8",
    )
    return payload


def fetch_telegram_preview_posts(
    channel_username: str,
    *,
    window_start: datetime,
    max_pages: int = 8,
    timeout_seconds: int = 20,
    sleep_seconds: float = 1.5,
    fetch_url: Callable[[str, int], str] | None = None,
) -> list[TelegramPost]:
    channel = _normalize_channel_username(channel_username).lstrip("@")
    safe_channel = urllib.parse.quote(channel, safe="")
    before: int | None = None
    posts_by_key: dict[tuple[str, int], TelegramPost] = {}
    active_fetch_url = fetch_url or _fetch_url
    cutoff = _as_utc(window_start)
    seen_before: set[int | None] = set()

    for page_number in range(max(1, int(max_pages or 8))):
        if before in seen_before:
            break
        seen_before.add(before)
        url = f"https://t.me/s/{safe_channel}" if before is None else f"https://t.me/s/{safe_channel}?before={before}"
        html = active_fetch_url(url, timeout_seconds)
        page_posts = parse_telegram_preview_posts(html, channel_username=channel)
        if not page_posts:
            break
        page_datetimes = [_parse_datetime(post.posted_at) for post in page_posts]
        for post in page_posts:
            posted_at = _parse_datetime(post.posted_at)
            if posted_at is None or posted_at >= cutoff:
                posts_by_key[post.key()] = post
        dated = [value for value in page_datetimes if value is not None]
        oldest_page_time = min(dated) if dated else None
        before = min(post.message_id for post in page_posts)
        if oldest_page_time is not None and oldest_page_time < cutoff:
            break
        if page_number + 1 < max_pages:
            time.sleep(max(0.0, float(sleep_seconds)))

    return sorted(posts_by_key.values(), key=lambda post: (_datetime_sort_key(post.posted_at), post.message_id), reverse=True)


def parse_telegram_preview_posts(html: str, *, channel_username: str) -> list[TelegramPost]:
    parser = _TelegramPreviewParser(channel_username=channel_username)
    parser.feed(html)
    parser.close()
    return parser.posts


def render_ai_transformation_source_packet_markdown(payload: dict[str, Any], *, max_posts: int = 120) -> str:
    window = payload.get("window", {})
    privacy = payload.get("privacy", {})
    counts = payload.get("source_counts", {})
    posts = list(payload.get("posts") or [])
    bucket_summary = list(payload.get("bucket_summary") or [])
    channels = list(payload.get("channels") or [])
    company_mentions = list(payload.get("company_mentions") or [])

    lines: list[str] = [
        "# AI transformation source packet",
        "",
        f"Generated: {payload.get('generated_at')}",
        f"Window: {window.get('start')} - {window.get('end')} ({window.get('days')} days)",
        "Purpose: private Markdown packet for an editor agent. It keeps source posts separate from PRM gold labels, dogfood evidence, and production ingestion.",
        "",
        "## Safety receipt",
        "",
        f"- live_public_telegram_preview_fetch={str(payload.get('inputs', {}).get('fetch_live_public_telegram_preview')).lower()}",
        f"- production_db_write={str(privacy.get('production_db_write')).lower()}",
        f"- telegram_service_start={str(privacy.get('telegram_service_start')).lower()}",
        f"- telegram_session_used={str(privacy.get('telegram_session_used')).lower()}",
        f"- provider_egress={str(privacy.get('provider_egress')).lower()}",
        f"- embeddings_or_vector_backend={str(privacy.get('embeddings_or_vector_backend')).lower()}",
        "- note: public Telegram preview does not expose private channels, comments, full reaction breakdown, or shares.",
        "",
        "## Coverage",
        "",
        f"- local_archive_posts={counts.get('local_archive_posts', 0)}",
        f"- live_preview_posts={counts.get('live_preview_posts', 0)}",
        f"- merged_posts={counts.get('merged_posts', 0)}",
        f"- relevant_posts={counts.get('relevant_posts', 0)}",
        "",
        "## Top liked channels used",
        "",
        "| channel | liked posts | local 3mo | live fetched | relevant | live status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for channel in channels:
        lines.append(
            "| {channel} | {likes} | {local} | {live} | {relevant} | {status} |".format(
                channel=channel.get("channel_username"),
                likes=channel.get("reaction_count", 0),
                local=channel.get("local_archive_posts", 0),
                live=channel.get("live_preview_posts", 0),
                relevant=channel.get("relevant_posts", 0),
                status=channel.get("live_status", "not_requested"),
            )
        )

    lines.extend(["", "## Reading map", ""])
    if bucket_summary:
        for item in bucket_summary:
            lines.append(f"- {item.get('bucket')}: {item.get('count')} posts")
    else:
        lines.append("- No topic-matched posts found in the selected channels/window.")

    lines.extend(["", "## Company and vendor mentions", ""])
    if company_mentions:
        for item in company_mentions[:30]:
            lines.append(f"- {item.get('name')}: {item.get('count')} posts")
    else:
        lines.append("- No deterministic company/vendor mentions extracted.")

    lines.extend(["", "## Editorial synthesis prompts", ""])
    lines.extend(_synthesis_prompt_lines(posts))
    lines.extend(
        [
            "",
            "## Post cards",
            "",
            "Posts are sorted by recency after deterministic topic scoring. Text is kept for private editorial use; source URLs remain the citation anchor.",
            "",
        ]
    )
    for index, post in enumerate(posts[: max(1, int(max_posts or 120))], start=1):
        lines.extend(_post_card_markdown(index, post))
    if len(posts) > max_posts:
        lines.extend(["", f"_Markdown truncated at {max_posts} posts; full post list is in JSON._"])
    lines.extend(
        [
            "",
            "## Your notes",
            "",
            "- What I agree with:",
            "- What contradicts what I saw myself:",
            "- My examples from projects/clients:",
            "- Strong post angle:",
            "- Claims to verify externally before publishing:",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


class _TelegramPreviewParser(HTMLParser):
    def __init__(self, *, channel_username: str):
        super().__init__(convert_charrefs=True)
        self.default_channel = _normalize_channel_username(channel_username)
        self.posts: list[TelegramPost] = []
        self._current: dict[str, Any] | None = None
        self._message_depth = 0
        self._text_depth = 0
        self._views_depth = 0
        self._reactions_depth = 0
        self._date_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "br" and self._current is not None and self._text_depth:
            self._current["text_parts"].append("\n")
            return
        data_post = attr.get("data-post", "")
        if tag == "div" and "js-widget_message" in classes and data_post and self._current is None:
            parsed = _parse_data_post(data_post, default_channel=self.default_channel)
            if parsed is None:
                return
            channel, message_id = parsed
            self._current = {
                "channel_username": channel,
                "message_id": message_id,
                "text_parts": [],
                "views_parts": [],
                "reaction_parts": [],
                "posted_at": "",
                "source_url": _message_url(channel, message_id),
                "is_service": "service_message" in classes,
            }
            self._message_depth = 1
            return
        if self._current is None:
            return

        self._message_depth += 1
        if self._text_depth:
            self._text_depth += 1
        elif "js-message_text" in classes and "js-message_reply_text" not in classes:
            self._text_depth = 1
        if self._views_depth:
            self._views_depth += 1
        elif "tgme_widget_message_views" in classes:
            self._views_depth = 1
        if self._reactions_depth:
            self._reactions_depth += 1
        elif "js-message_reactions" in classes:
            self._reactions_depth = 1
        if tag == "a" and "tgme_widget_message_date" in classes:
            href = attr.get("href", "")
            if href:
                self._date_href = href
                self._current["source_url"] = href
        if tag == "time" and attr.get("datetime"):
            self._current["posted_at"] = attr["datetime"]

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        if self._text_depth:
            self._current["text_parts"].append(data)
        if self._views_depth:
            self._current["views_parts"].append(data)
        if self._reactions_depth:
            self._current["reaction_parts"].append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and self._current is not None and self._text_depth:
            self._current["text_parts"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._text_depth:
            self._text_depth -= 1
        if self._views_depth:
            self._views_depth -= 1
        if self._reactions_depth:
            self._reactions_depth -= 1
        self._message_depth -= 1
        if self._message_depth <= 0:
            self._finish_current()

    def _finish_current(self) -> None:
        if self._current is None:
            return
        current = self._current
        self._current = None
        self._message_depth = 0
        self._text_depth = 0
        self._views_depth = 0
        self._reactions_depth = 0
        self._date_href = None
        text = _clean_text("".join(current["text_parts"]))
        if current.get("is_service") or not text:
            return
        self.posts.append(
            TelegramPost(
                channel_username=current["channel_username"],
                message_id=int(current["message_id"]),
                posted_at=_iso_z(_parse_datetime(current.get("posted_at")) or datetime.now(timezone.utc)),
                source_url=current.get("source_url") or _message_url(current["channel_username"], current["message_id"]),
                text=text,
                views=_parse_compact_number("".join(current["views_parts"])),
                reactions=_parse_reaction_total(" ".join(current["reaction_parts"])),
            )
        )


def _top_reaction_channels(connection: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "reaction_sync_state"):
        return []
    rows = connection.execute(
        """
        SELECT channel_username, applied_at
        FROM reaction_sync_state
        WHERE channel_username IS NOT NULL AND length(trim(channel_username)) > 0
        """
    ).fetchall()
    counts: Counter[str] = Counter()
    latest: dict[str, str] = {}
    for row in rows:
        channel = _normalize_channel_username(row["channel_username"])
        counts[channel] += 1
        applied_at = str(row["applied_at"] or "")
        if applied_at and applied_at > latest.get(channel, ""):
            latest[channel] = applied_at
    return [
        {
            "channel_username": channel,
            "reaction_count": count,
            "latest_reaction_at": latest.get(channel),
        }
        for channel, count in sorted(counts.items(), key=lambda item: (-item[1], latest.get(item[0], ""), item[0]))[:limit]
    ]


def _load_local_archive_posts(
    connection: sqlite3.Connection,
    *,
    channels: list[dict[str, Any]],
    window_start: datetime,
) -> list[TelegramPost]:
    if not channels or not _table_exists(connection, "raw_posts"):
        return []
    connection.row_factory = sqlite3.Row
    channel_values = [_normalize_channel_username(item["channel_username"]) for item in channels]
    placeholders = ",".join("?" for _ in channel_values)
    has_posts = _table_exists(connection, "posts")
    if has_posts:
        sql = f"""
            SELECT r.channel_username, r.message_id, r.posted_at,
                   COALESCE(NULLIF(p.content, ''), NULLIF(r.text, ''), NULLIF(r.media_caption, ''), '') AS text,
                   r.message_url, r.view_count
            FROM raw_posts r
            LEFT JOIN posts p ON p.raw_post_id = r.id
            WHERE r.channel_username IN ({placeholders})
            ORDER BY r.posted_at DESC
        """
    else:
        sql = f"""
            SELECT r.channel_username, r.message_id, r.posted_at,
                   COALESCE(NULLIF(r.text, ''), NULLIF(r.media_caption, ''), '') AS text,
                   r.message_url, r.view_count
            FROM raw_posts r
            WHERE r.channel_username IN ({placeholders})
            ORDER BY r.posted_at DESC
        """
    cutoff = _as_utc(window_start)
    posts: list[TelegramPost] = []
    for row in connection.execute(sql, tuple(channel_values)).fetchall():
        posted_at = _parse_datetime(row["posted_at"])
        if posted_at is None or posted_at < cutoff:
            continue
        channel = _normalize_channel_username(row["channel_username"])
        message_id = _int(row["message_id"])
        text = _clean_text(row["text"])
        if not channel or message_id <= 0 or not text:
            continue
        posts.append(
            TelegramPost(
                channel_username=channel,
                message_id=message_id,
                posted_at=_iso_z(posted_at),
                source_url=str(row["message_url"] or "") or _message_url(channel, message_id),
                text=text,
                views=_optional_int(row["view_count"]),
                source="local_archive_read_only",
            )
        )
    return posts


def _merge_posts(*, local_posts: list[TelegramPost], live_posts: list[TelegramPost]) -> list[TelegramPost]:
    merged: dict[tuple[str, int], TelegramPost] = {}
    for post in local_posts:
        merged[post.key()] = post
    for post in live_posts:
        existing = merged.get(post.key())
        if existing is None or len(post.text) >= len(existing.text):
            merged[post.key()] = post
    return sorted(merged.values(), key=lambda post: (_datetime_sort_key(post.posted_at), post.message_id), reverse=True)


def _rank_relevant_posts(posts: Iterable[TelegramPost], *, window_start: datetime) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    cutoff = _as_utc(window_start)
    for post in posts:
        posted_at = _parse_datetime(post.posted_at)
        if posted_at is not None and posted_at < cutoff:
            continue
        score, buckets, matched_terms = _classify_text(post.text)
        if score < 3:
            continue
        card = post.to_dict()
        card.update(
            {
                "topic_score": score,
                "buckets": buckets,
                "matched_terms": matched_terms[:16],
                "company_mentions": _extract_company_mentions(post.text),
                "stance": _stance_from_buckets(buckets),
            }
        )
        cards.append(card)
    return sorted(
        cards,
        key=lambda item: (
            _datetime_sort_key(item.get("posted_at")),
            int(item.get("topic_score") or 0),
            int(item.get("reactions") or 0),
            int(item.get("views") or 0),
        ),
        reverse=True,
    )


def _classify_text(text: str) -> tuple[int, list[str], list[str]]:
    lowered = text.casefold()
    buckets: set[str] = set()
    matched: list[str] = []
    score = 0

    def apply(bucket: str, terms: tuple[str, ...], weight: int) -> None:
        nonlocal score
        hits = [term for term in terms if term in lowered]
        if hits:
            buckets.add(bucket)
            matched.extend(hits[:4])
            score += weight + min(2, len(hits) - 1)

    apply("ai_adoption", _AI_TERMS, 2)
    apply("company_transformation", _COMPANY_TRANSFORMATION_TERMS, 2)
    apply("growth_or_roi", _GROWTH_TERMS, 2)
    apply("failed_or_stalled", _FAILURE_TERMS, 2)
    apply("implementation_reasons", _REASON_TERMS, 1)
    apply("workforce_layoffs", _LAYOFF_TERMS, 2)
    apply("workforce_hiring", _HIRING_TERMS, 2)
    apply("tooling_and_agents", _TOOLING_TERMS, 1)

    if "ai_adoption" not in buckets and not ({"workforce_layoffs", "workforce_hiring"} & buckets):
        score -= 2
    if "ai_adoption" in buckets and not (set(buckets) - {"ai_adoption", "tooling_and_agents"}):
        score -= 2
    return max(0, score), sorted(buckets), sorted(set(matched), key=matched.index)


def _post_card(post: dict[str, Any]) -> dict[str, Any]:
    text = _clean_text(post.get("text"))
    return {
        **post,
        "excerpt": _truncate(text, 600),
    }


def _channel_summary(
    *,
    channels: list[dict[str, Any]],
    local_posts: list[TelegramPost],
    live_posts: list[TelegramPost],
    relevant_posts: list[dict[str, Any]],
    live_status: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    local_counts = Counter(_normalize_channel_username(post.channel_username) for post in local_posts)
    live_counts = Counter(_normalize_channel_username(post.channel_username) for post in live_posts)
    relevant_counts = Counter(_normalize_channel_username(post.get("channel_username")) for post in relevant_posts)
    summary: list[dict[str, Any]] = []
    for channel in channels:
        normalized = _normalize_channel_username(channel["channel_username"])
        status = live_status.get(normalized, {"status": "not_requested"})
        summary.append(
            {
                **channel,
                "channel_username": normalized,
                "local_archive_posts": local_counts[normalized],
                "live_preview_posts": live_counts[normalized],
                "relevant_posts": relevant_counts[normalized],
                "live_status": status.get("status"),
                "live_error": status.get("error"),
            }
        )
    return summary


def _bucket_summary(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for post in posts:
        counts.update(post.get("buckets") or [])
    return [{"bucket": bucket, "count": count} for bucket, count in counts.most_common()]


def _company_mentions_summary(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for post in posts:
        counts.update(post.get("company_mentions") or [])
    return [{"name": name, "count": count} for name, count in counts.most_common()]


def _synthesis_prompt_lines(posts: list[dict[str, Any]]) -> list[str]:
    bucket_to_posts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        for bucket in post.get("buckets") or []:
            bucket_to_posts[bucket].append(post)
    prompts = [
        "- What came true: start from posts tagged `growth_or_roi` and `ai_adoption`; separate measured results from author confidence.",
        "- What failed or stalled: use `failed_or_stalled` plus `implementation_reasons`; look for cost, workflow, data quality, management, and tooling constraints.",
        "- Where growth exists: compare posts with concrete metrics, usage, sales, cost savings, or shipped internal tools.",
        "- Where growth is absent: collect claims about no productivity lift, expensive pilots, model limits, and organizational mismatch.",
        "- Hiring vs layoffs: use `workforce_hiring` and `workforce_layoffs`; do not infer company actions unless the post names them.",
    ]
    for bucket in ("growth_or_roi", "failed_or_stalled", "workforce_layoffs", "workforce_hiring"):
        examples = bucket_to_posts.get(bucket, [])[:3]
        if examples:
            refs = ", ".join(f"{post.get('channel_username')}/{post.get('message_id')}" for post in examples)
            prompts.append(f"- Seed examples for `{bucket}`: {refs}")
    return prompts


def _post_card_markdown(index: int, post: dict[str, Any]) -> list[str]:
    text = _truncate(_clean_text(post.get("text")), 3500)
    lines = [
        f"### {index}. {post.get('channel_username')} / {post.get('message_id')}",
        "",
        f"- date: {post.get('posted_at')}",
        f"- source: {post.get('source_url')}",
        f"- source_kind: {post.get('source')}",
        f"- views: {post.get('views') if post.get('views') is not None else 'n/a'}; reactions: {post.get('reactions') if post.get('reactions') is not None else 'n/a'}",
        f"- buckets: {', '.join(post.get('buckets') or [])}",
        f"- stance: {post.get('stance')}",
        f"- matched_terms: {', '.join(post.get('matched_terms') or [])}",
    ]
    mentions = post.get("company_mentions") or []
    if mentions:
        lines.append(f"- company_mentions: {', '.join(mentions)}")
    lines.extend(["", text, ""])
    return lines


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    absolute = db_path.resolve()
    connection = sqlite3.connect(f"file:{absolute}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _fetch_url(url: str, timeout_seconds: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "telegram-research-agent-source-packet/1.0 (+read-only public preview)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"failed to fetch {url}: {exc}") from exc


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_data_post(value: str, *, default_channel: str) -> tuple[str, int] | None:
    if "/" not in value:
        return None
    raw_channel, raw_message_id = value.rsplit("/", 1)
    match = re.search(r"\d+", raw_message_id)
    if not match:
        return None
    channel = _normalize_channel_username(raw_channel or default_channel)
    return channel, int(match.group(0))


def _normalize_channel_username(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("https://t.me/s/"):
        text = text.split("https://t.me/s/", 1)[1]
    elif text.startswith("https://t.me/"):
        text = text.split("https://t.me/", 1)[1]
    text = text.split("?", 1)[0].split("/", 1)[0].strip()
    if not text:
        return ""
    return text if text.startswith("@") else f"@{text}"


def _message_url(channel_username: str, message_id: int) -> str:
    return f"https://t.me/{_normalize_channel_username(channel_username).lstrip('@')}/{int(message_id)}"


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _datetime_sort_key(value: Any) -> str:
    parsed = _parse_datetime(value)
    return _iso_z(parsed) if parsed is not None else ""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value or ""))
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate(value: str, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 15)].rstrip() + "\n[truncated]"


def _parse_compact_number(value: str) -> int | None:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)([KkMm]?)", text)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    suffix = match.group(2).casefold()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def _parse_reaction_total(value: str) -> int | None:
    total = 0
    for match in re.finditer(r"(?<![A-Za-zА-Яа-я])(\d+(?:[.,]\d+)?[KkMm]?)", str(value or "")):
        parsed = _parse_compact_number(match.group(1))
        if parsed is not None:
            total += parsed
    return total or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_company_mentions(text: str) -> list[str]:
    lowered = text.casefold()
    mentions: list[str] = []
    for canonical, variants in _COMPANY_VARIANTS.items():
        if any(variant.casefold() in lowered for variant in variants):
            mentions.append(canonical)
    return mentions


def _stance_from_buckets(buckets: list[str]) -> str:
    bucket_set = set(buckets)
    if {"growth_or_roi", "failed_or_stalled"} <= bucket_set:
        return "mixed"
    if "failed_or_stalled" in bucket_set or "workforce_layoffs" in bucket_set:
        return "skeptical_or_negative"
    if "growth_or_roi" in bucket_set or "workforce_hiring" in bucket_set:
        return "positive_or_adoption"
    return "evidence_gathering"


_AI_TERMS = (
    "ai",
    "ии",
    "искусственн",
    "нейросет",
    "llm",
    "gpt",
    "claude",
    "openai",
    "anthropic",
    "copilot",
    "agent",
    "агент",
    "генератив",
    "модель",
    "модели",
)
_COMPANY_TRANSFORMATION_TERMS = (
    "компан",
    "корпорац",
    "бизнес",
    "enterprise",
    "организац",
    "внедр",
    "трансформац",
    "автоматизац",
    "процесс",
    "операцион",
    "workflow",
    "рабоч",
    "сотрудник",
    "разработчик",
)
_GROWTH_TERMS = (
    "рост",
    "прирост",
    "выруч",
    "прибыл",
    "маржин",
    "эконом",
    "roi",
    "productivity",
    "производительн",
    "эффективн",
    "ускор",
    "сократил",
    "снизил",
    "growth",
    "revenue",
)
_FAILURE_TERMS = (
    "не получилось",
    "не получилось",
    "не взлет",
    "не работает",
    "нет прироста",
    "без прироста",
    "провал",
    "провалил",
    "ошиб",
    "хуже",
    "дорог",
    "стоим",
    "лимит",
    "разочаров",
    "неюзаб",
    "fail",
    "failed",
    "stall",
)
_REASON_TERMS = (
    "почему",
    "причин",
    "данн",
    "качество",
    "менедж",
    "интеграц",
    "процесс",
    "культура",
    "security",
    "безопас",
    "стоимость",
    "лимит",
    "guardrail",
)
_LAYOFF_TERMS = (
    "увольн",
    "сокращ",
    "layoff",
    "laid off",
    "job cut",
    "job cuts",
    "заменит людей",
    "заменяют людей",
    "без людей",
)
_HIRING_TERMS = (
    "наним",
    "найм",
    "ваканси",
    "hiring",
    "hire",
    "recruit",
    "jobs",
    "штат",
    "команда раст",
)
_TOOLING_TERMS = (
    "tool",
    "тул",
    "кодинг",
    "coding",
    "developer",
    "разработ",
    "copilot",
    "cursor",
    "devin",
    "автоном",
)
_COMPANY_VARIANTS = {
    "OpenAI": ("openai", "опенаи", "опенай"),
    "Anthropic": ("anthropic", "антропик", "claude", "клод"),
    "Microsoft": ("microsoft", "майкрософт"),
    "Google": ("google", "гугл"),
    "Meta": ("meta", "мета"),
    "Amazon": ("amazon", "aws", "амазон"),
    "Apple": ("apple", "эппл"),
    "NVIDIA": ("nvidia", "энвид"),
    "IBM": ("ibm",),
    "Salesforce": ("salesforce",),
    "Klarna": ("klarna", "кларна"),
    "Shopify": ("shopify",),
    "Duolingo": ("duolingo",),
    "Accenture": ("accenture",),
    "Deloitte": ("deloitte",),
    "McKinsey": ("mckinsey", "маккинзи"),
    "JPMorgan": ("jpmorgan", "jp morgan", "j.p. morgan"),
    "Goldman Sachs": ("goldman",),
    "Oracle": ("oracle",),
    "SAP": ("sap",),
    "ServiceNow": ("servicenow",),
    "Adobe": ("adobe",),
    "Cursor": ("cursor",),
    "Kimi": ("kimi",),
}
