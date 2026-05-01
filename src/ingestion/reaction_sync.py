import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from config.settings import Settings
from db.migrate import record_feedback, record_post_tag


LOGGER = logging.getLogger(__name__)
REACTION_SOURCE = "telegram_reaction"


@dataclass(frozen=True)
class ReactionRule:
    tag: str | None = None
    feedback: str | None = None


REACTION_RULES: dict[str, ReactionRule] = {
    "🔥": ReactionRule(tag="strong", feedback="marked_important"),
    "⭐": ReactionRule(tag="strong", feedback="marked_important"),
    "❤": ReactionRule(tag="strong", feedback="marked_important"),
    "❤️": ReactionRule(tag="strong", feedback="marked_important"),
    "👍": ReactionRule(tag="interesting", feedback="marked_important"),
    "👏": ReactionRule(tag="interesting", feedback="marked_important"),
    "👀": ReactionRule(tag="read_later"),
    "🤔": ReactionRule(tag="read_later"),
    "⚡": ReactionRule(tag="try_in_project"),
    "🛠": ReactionRule(tag="try_in_project"),
    "🛠️": ReactionRule(tag="try_in_project"),
    "✅": ReactionRule(tag="try_in_project", feedback="acted_on"),
    "👎": ReactionRule(tag="low_signal", feedback="skipped"),
    "💩": ReactionRule(tag="low_signal", feedback="skipped"),
    "❌": ReactionRule(tag="low_signal", feedback="skipped"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_reaction_emoji(reaction: Any) -> str | None:
    if reaction is None:
        return None
    if isinstance(reaction, str):
        return reaction.strip() or None

    emoticon = getattr(reaction, "emoticon", None)
    if isinstance(emoticon, str) and emoticon.strip():
        return emoticon.strip()

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

    for peer_reaction in getattr(reactions, "recent_reactions", []) or []:
        if not _reaction_belongs_to_self(peer_reaction, self_user_id):
            continue
        emoji = _normalize_reaction_emoji(getattr(peer_reaction, "reaction", None))
        if emoji:
            emojis.add(emoji)
    return emojis


async def _fetch_self_reaction_emojis(client: Any, entity: Any, message_id: int, self_user_id: int | None) -> set[str]:
    try:
        from telethon.tl.functions.messages import GetMessageReactionsListRequest

        offset = ""
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
            emojis = _extract_self_reactions_from_list_result(result, self_user_id)
            if emojis:
                return emojis
            next_offset = getattr(result, "next_offset", None)
            if not next_offset:
                break
            offset = str(next_offset)
    except Exception:
        LOGGER.debug("Reaction list request failed channel_entity=%s message_id=%s", entity, message_id, exc_info=True)

    try:
        message = await client.get_messages(entity, ids=message_id)
        return _extract_self_reactions_from_message(message, self_user_id)
    except Exception:
        LOGGER.debug("Message reaction fallback failed channel_entity=%s message_id=%s", entity, message_id, exc_info=True)
        return set()


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
    action_key: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM reaction_sync_state
        WHERE source = ?
          AND lower(channel_username) = lower(?)
          AND message_id = ?
          AND emoji = ?
          AND action_key = ?
        LIMIT 1
        """,
        (REACTION_SOURCE, channel_username, message_id, emoji, action_key),
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
        rule = REACTION_RULES.get(emoji or "")
        if emoji is None or rule is None:
            summary["skipped_unknown"] += 1
            continue

        action_key = _action_key(rule)
        if _state_exists(
            connection,
            channel_username=channel_username,
            message_id=message_id,
            emoji=emoji,
            action_key=action_key,
        ):
            summary["skipped_existing"] += 1
            continue

        summary["matched_reactions"] += 1
        if rule.tag:
            record_post_tag(connection, post_id, rule.tag, note=f"telegram reaction {emoji}")
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


def _load_candidate_posts(connection: sqlite3.Connection, days: int, limit: int) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    return connection.execute(
        """
        SELECT
            p.id AS post_id,
            p.channel_username,
            r.message_id
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.posted_at >= ?
          AND r.message_id IS NOT NULL
          AND p.channel_username IS NOT NULL
        ORDER BY p.posted_at DESC, p.id DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()


async def sync_reactions(settings: Settings, *, days: int = 14, limit: int = 300) -> dict[str, int]:
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

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        candidates = _load_candidate_posts(connection, days=days, limit=limit)

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

                    summary["posts_with_reactions"] += 1
                    applied = apply_reaction_feedback(
                        connection,
                        post_id=int(row["post_id"]),
                        channel_username=channel_username,
                        message_id=int(row["message_id"]),
                        emojis=emojis,
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

    return summary
