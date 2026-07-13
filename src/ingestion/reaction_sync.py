import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from config.settings import Settings
from db.migrate import record_feedback, record_post_tag
from output.reporting_period import ReportingPeriod, register_reporting_period_sqlite


LOGGER = logging.getLogger(__name__)
REACTION_SOURCE = "telegram_reaction"
OPERATOR_INTEREST_TAG = "interesting"
OPERATOR_INTEREST_FEEDBACK = "operator_marked_interesting"


@dataclass(frozen=True)
class ReactionRule:
    tag: str | None = None
    feedback: str | None = None


class ReactionVisibilityUnverifiedError(RuntimeError):
    """Raised when neither Telegram lookup can attest personal visibility."""


@dataclass(frozen=True)
class ObservedPersonalPost:
    """One currently visible personal-reaction post in a bounded sync run.

    ``raw_emojis`` is audit provenance only.  Ranking consumers must treat the
    whole record as one positive post-level interest signal regardless of how
    many emoji values Telegram returned.
    """

    post_id: int
    channel_username: str
    message_id: int
    posted_at: str
    raw_emojis: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "post_id": self.post_id,
            "channel_username": self.channel_username,
            "message_id": self.message_id,
            "posted_at": self.posted_at,
            "raw_emojis": list(self.raw_emojis),
        }


@dataclass(frozen=True)
class ReactionSyncOutcome:
    """Additive same-run visibility outcome for reaction personalization.

    The legacy ``sync_reactions`` API deliberately returns only ``summary``.
    IRX-3 callers opt into this richer result so stale materialized feedback
    rows cannot be mistaken for reactions that were visible in the current
    Telegram snapshot.
    """

    summary: Mapping[str, int]
    observed_personal_posts: tuple[ObservedPersonalPost, ...]
    candidate_count: int
    checked_count: int
    coverage_complete: bool
    visibility_verified: bool

    def count_summary(self) -> dict[str, int]:
        return {str(key): int(value) for key, value in self.summary.items()}

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.count_summary(),
            "observed_personal_posts": [
                post.to_dict() for post in self.observed_personal_posts
            ],
            "candidate_count": self.candidate_count,
            "checked_count": self.checked_count,
            "coverage_complete": self.coverage_complete,
            "visibility_verified": self.visibility_verified,
        }


OPERATOR_INTEREST_RULE = ReactionRule(
    tag=OPERATOR_INTEREST_TAG,
    feedback=OPERATOR_INTEREST_FEEDBACK,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_utc_text(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reaction source timestamp must include an explicit UTC offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_reaction_emoji(reaction: Any) -> str | None:
    if reaction is None:
        return None
    if isinstance(reaction, str):
        return reaction.strip() or None

    emoticon = getattr(reaction, "emoticon", None)
    if isinstance(emoticon, str) and emoticon.strip():
        return emoticon.strip()

    document_id = getattr(reaction, "document_id", None)
    if document_id is not None:
        opaque_id = str(document_id).strip()
        if opaque_id:
            return f"custom_emoji:{opaque_id}"

    return None


def _peer_matches_user(peer: Any, self_user_id: int | None) -> bool:
    if self_user_id is None or peer is None:
        return False
    return getattr(peer, "user_id", None) == self_user_id


def _reaction_belongs_to_self(peer_reaction: Any, self_user_id: int | None) -> bool:
    if getattr(peer_reaction, "my", False):
        return True
    return _peer_matches_user(getattr(peer_reaction, "peer_id", None), self_user_id)


def _extract_self_reactions_from_list_result(result: Any, self_user_id: int | None) -> set[str]:
    emojis: set[str] = set()
    for peer_reaction in getattr(result, "reactions", []) or []:
        if not _reaction_belongs_to_self(peer_reaction, self_user_id):
            continue
        emoji = _normalize_reaction_emoji(getattr(peer_reaction, "reaction", None))
        if emoji:
            emojis.add(emoji)
    return emojis


def _extract_self_reactions_from_message(message: Any, self_user_id: int | None) -> set[str]:
    emojis: set[str] = set()
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return emojis

    # ``MessageReactions.results`` is the complete aggregate reaction list.
    # Telegram marks the current operator's own entries with ``chosen_order``;
    # the aggregate count by itself is deliberately ignored.
    for reaction_count in getattr(reactions, "results", []) or []:
        if getattr(reaction_count, "chosen_order", None) is None:
            continue
        emoji = _normalize_reaction_emoji(getattr(reaction_count, "reaction", None))
        if emoji:
            emojis.add(emoji)

    for peer_reaction in getattr(reactions, "recent_reactions", []) or []:
        if not _reaction_belongs_to_self(peer_reaction, self_user_id):
            continue
        emoji = _normalize_reaction_emoji(getattr(peer_reaction, "reaction", None))
        if emoji:
            emojis.add(emoji)
    return emojis


async def _fetch_self_reaction_emojis(client: Any, entity: Any, message_id: int, self_user_id: int | None) -> set[str]:
    primary_error: Exception | None = None
    try:
        from telethon.tl.functions.messages import GetMessageReactionsListRequest

        offset = ""
        emojis: set[str] = set()
        for _page in range(5):
            result = await client(
                GetMessageReactionsListRequest(
                    peer=entity,
                    id=message_id,
                    reaction=None,
                    offset=offset,
                    limit=100,
                )
            )
            if result is None:
                raise RuntimeError("Telegram reaction-list lookup returned no result")
            emojis.update(
                _extract_self_reactions_from_list_result(result, self_user_id)
            )
            next_offset = getattr(result, "next_offset", None)
            if not next_offset:
                return emojis
            offset = str(next_offset)
        primary_error = RuntimeError(
            "Telegram reaction-list lookup exceeded the bounded page limit"
        )
    except Exception as exc:
        primary_error = exc
        LOGGER.debug("Reaction list request failed channel_entity=%s message_id=%s", entity, message_id, exc_info=True)

    try:
        message = await client.get_messages(entity, ids=message_id)
        if message is None:
            raise RuntimeError("Telegram message lookup returned no message")
        emojis = _extract_self_reactions_from_message(message, self_user_id)
        if emojis:
            # A recent self entry is sufficient to prove the positive
            # post-level signal even when the full list lookup failed.
            return emojis
        reactions = getattr(message, "reactions", None)
        if reactions is None or hasattr(reactions, "results"):
            # No reaction container, or a complete own-chosen marker list,
            # can attest the absence of a personal reaction.  An empty
            # ``recent_reactions`` subset alone cannot.
            return set()
        raise ReactionVisibilityUnverifiedError(
            "message fallback exposed only an incomplete recent reaction subset"
        )
    except Exception as fallback_error:
        LOGGER.debug("Message reaction fallback failed channel_entity=%s message_id=%s", entity, message_id, exc_info=True)
        primary_name = type(primary_error).__name__ if primary_error is not None else "unknown"
        failure = ReactionVisibilityUnverifiedError(
            "personal reaction visibility could not be verified "
            f"for message {message_id} (primary={primary_name}, "
            f"fallback={type(fallback_error).__name__})"
        )
        raise failure from fallback_error


def _action_key(rule: ReactionRule) -> str:
    parts: list[str] = []
    if rule.tag:
        parts.append(f"tag:{rule.tag}")
    if rule.feedback:
        parts.append(f"feedback:{rule.feedback}")
    return "|".join(parts)


def _state_exists(
    connection: sqlite3.Connection,
    *,
    channel_username: str,
    message_id: int,
    emoji: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM reaction_sync_state
        WHERE source = ?
          AND lower(channel_username) = lower(?)
          AND message_id = ?
          AND emoji = ?
        LIMIT 1
        """,
        (REACTION_SOURCE, channel_username, message_id, emoji),
    ).fetchone()
    return row is not None


def _mark_state_applied(
    connection: sqlite3.Connection,
    *,
    channel_username: str,
    message_id: int,
    emoji: str,
    action_key: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO reaction_sync_state
            (source, channel_username, message_id, emoji, action_key, applied_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (REACTION_SOURCE, channel_username, message_id, emoji, action_key, _utc_now()),
    )
    connection.commit()


def apply_reaction_feedback(
    connection: sqlite3.Connection,
    *,
    post_id: int,
    channel_username: str,
    message_id: int,
    emojis: set[str],
) -> dict[str, int]:
    summary = {
        "matched_reactions": 0,
        "applied_tags": 0,
        "applied_feedback": 0,
        "skipped_unknown": 0,
        "skipped_existing": 0,
    }

    for raw_emoji in sorted(emojis):
        emoji = _normalize_reaction_emoji(raw_emoji)
        if emoji is None:
            summary["skipped_unknown"] += 1
            continue

        rule = OPERATOR_INTEREST_RULE
        action_key = _action_key(rule)
        if _state_exists(
            connection,
            channel_username=channel_username,
            message_id=message_id,
            emoji=emoji,
        ):
            summary["skipped_existing"] += 1
            continue

        summary["matched_reactions"] += 1
        if rule.tag:
            record_post_tag(
                connection,
                post_id,
                rule.tag,
                note=f"operator telegram reaction {emoji}",
            )
            summary["applied_tags"] += 1
        if rule.feedback:
            record_feedback(connection, post_id, rule.feedback)
            summary["applied_feedback"] += 1

        _mark_state_applied(
            connection,
            channel_username=channel_username,
            message_id=message_id,
            emoji=emoji,
            action_key=action_key,
        )

    return summary


def _merge_summary(target: dict[str, int], update: dict[str, int]) -> None:
    for key, value in update.items():
        target[key] = target.get(key, 0) + int(value or 0)


def _load_candidate_posts(
    connection: sqlite3.Connection,
    days: int,
    limit: int,
    *,
    reporting_period: ReportingPeriod | None = None,
) -> list[sqlite3.Row]:
    rows, _candidate_count = _load_candidate_posts_with_count(
        connection,
        days,
        limit,
        reporting_period=reporting_period,
    )
    return rows


def _load_candidate_posts_with_count(
    connection: sqlite3.Connection,
    days: int,
    limit: int,
    *,
    reporting_period: ReportingPeriod | None = None,
) -> tuple[list[sqlite3.Row], int]:
    """Load a bounded page and the exact eligible population size."""

    clean_limit = max(1, int(limit or 300))
    if reporting_period is not None:
        register_reporting_period_sqlite(connection)
        period = reporting_period.to_dict()
        where_sql = """
            reporting_utc_micros(p.posted_at) >= reporting_utc_micros(?)
            AND reporting_utc_micros(p.posted_at) < reporting_utc_micros(?)
            AND r.message_id IS NOT NULL
            AND p.channel_username IS NOT NULL
        """
        where_params: tuple[object, ...] = (
            period["analysis_period_start"],
            period["analysis_period_end"],
        )
        order_sql = "reporting_utc_micros(p.posted_at) DESC, p.id DESC"
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        where_sql = """
            p.posted_at >= ?
            AND r.message_id IS NOT NULL
            AND p.channel_username IS NOT NULL
        """
        where_params = (cutoff,)
        order_sql = "p.posted_at DESC, p.id DESC"

    candidate_count = int(
        connection.execute(
            f"""
            SELECT COUNT(*)
            FROM posts p
            INNER JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE {where_sql}
            """,
            where_params,
        ).fetchone()[0]
    )
    rows = connection.execute(
        f"""
        SELECT
            p.id AS post_id,
            p.channel_username,
            p.posted_at,
            r.message_id
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ?
        """,
        (*where_params, clean_limit),
    ).fetchall()
    return rows, candidate_count


async def sync_reactions(
    settings: Settings,
    *,
    days: int = 14,
    limit: int = 300,
    reporting_period: ReportingPeriod | None = None,
) -> dict[str, int]:
    """Preserve the legacy count-only reaction-sync contract."""

    outcome = await sync_reactions_with_outcome(
        settings,
        days=days,
        limit=limit,
        reporting_period=reporting_period,
    )
    return outcome.count_summary()


async def sync_reactions_with_outcome(
    settings: Settings,
    *,
    days: int = 14,
    limit: int = 300,
    reporting_period: ReportingPeriod | None = None,
) -> ReactionSyncOutcome:
    """Sync reactions and attest the personal reactions visible in this run."""

    from ingestion.telegram_client import make_client

    summary = {
        "posts_checked": 0,
        "posts_with_reactions": 0,
        "matched_reactions": 0,
        "applied_tags": 0,
        "applied_feedback": 0,
        "skipped_unknown": 0,
        "skipped_existing": 0,
        "errors": 0,
    }
    observed: dict[tuple[str, int], dict[str, object]] = {}

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        candidates, candidate_count = _load_candidate_posts_with_count(
            connection,
            days=days,
            limit=limit,
            reporting_period=reporting_period,
        )

        client = await make_client(settings)
        try:
            me = await client.get_me()
            self_user_id = getattr(me, "id", None)
            entity_cache: dict[str, Any] = {}

            for row in candidates:
                summary["posts_checked"] += 1
                channel_username = str(row["channel_username"])
                try:
                    entity = entity_cache.get(channel_username)
                    if entity is None:
                        entity = await client.get_entity(channel_username)
                        entity_cache[channel_username] = entity

                    emojis = await _fetch_self_reaction_emojis(
                        client,
                        entity,
                        int(row["message_id"]),
                        self_user_id,
                    )
                    if not emojis:
                        continue

                    normalized_emojis = {
                        emoji
                        for raw_emoji in emojis
                        if (emoji := _normalize_reaction_emoji(raw_emoji)) is not None
                    }
                    if not normalized_emojis:
                        continue
                    identity = (
                        _normalized_channel_identity(channel_username),
                        int(row["message_id"]),
                    )
                    if identity not in observed:
                        summary["posts_with_reactions"] += 1
                    audit = observed.setdefault(
                        identity,
                        {
                            "post_id": int(row["post_id"]),
                            "channel_username": channel_username,
                            "message_id": int(row["message_id"]),
                            "posted_at": str(row["posted_at"] or ""),
                            "raw_emojis": set(),
                        },
                    )
                    raw_emojis = audit["raw_emojis"]
                    assert isinstance(raw_emojis, set)
                    raw_emojis.update(normalized_emojis)
                    applied = apply_reaction_feedback(
                        connection,
                        post_id=int(row["post_id"]),
                        channel_username=channel_username,
                        message_id=int(row["message_id"]),
                        emojis=normalized_emojis,
                    )
                    _merge_summary(summary, applied)
                except Exception:
                    summary["errors"] += 1
                    LOGGER.warning(
                        "Reaction sync failed for channel=%s message_id=%s",
                        channel_username,
                        row["message_id"],
                        exc_info=True,
                    )
        finally:
            await client.disconnect()

    checked_count = int(summary["posts_checked"])
    coverage_complete = checked_count == candidate_count
    visibility_verified = coverage_complete and int(summary["errors"]) == 0
    observed_posts = tuple(
        ObservedPersonalPost(
            post_id=int(audit["post_id"]),
            channel_username=str(audit["channel_username"]),
            message_id=int(audit["message_id"]),
            posted_at=_canonical_utc_text(audit["posted_at"]),
            raw_emojis=tuple(sorted(str(item) for item in audit["raw_emojis"])),
        )
        for _identity, audit in sorted(observed.items())
    )
    return ReactionSyncOutcome(
        summary=dict(summary),
        observed_personal_posts=observed_posts,
        candidate_count=candidate_count,
        checked_count=checked_count,
        coverage_complete=coverage_complete,
        visibility_verified=visibility_verified,
    )


def _normalized_channel_identity(value: object) -> str:
    return str(value or "").strip().lstrip("@").casefold()
