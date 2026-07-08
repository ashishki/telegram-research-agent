from __future__ import annotations

import json
import re
import sqlite3
from typing import Iterable


MARKET_BUSINESS_CHANNELS = (
    "@its_capitan",
    "@exitsexist",
    "@leadgenvalley",
    "@cryptoEssay",
    "@huntermikevolkov",
)

MARKET_CONTEXT_ATOM_TYPES = (
    "market_signal",
    "workflow_pattern",
    "case_study",
    "opinion_shift",
    "risk_warning",
)

PAIN_TERMS = (
    "pain",
    "боль",
    "problem",
    "проблем",
    "manual",
    "вручную",
    "руками",
    "slow",
    "медленно",
    "дорого",
    "expensive",
    "cac",
    "ltv",
)
BUYING_TERMS = (
    "pay",
    "плат",
    "pricing",
    "price",
    "budget",
    "mrr",
    "arr",
    "revenue",
    "$",
    "демо",
    "demo",
    "conversion",
    "reply rate",
    "open rate",
    "hiring",
)
DISTRIBUTION_TERMS = (
    "seo",
    "search",
    "поиск",
    "organic",
    "cold outreach",
    "founder-led",
    "email",
    "linkedin",
    "youtube",
    "telegram",
    "product hunt",
    "ads",
    "реклама",
)
WORKFLOW_TERMS = (
    "workflow",
    "воронк",
    "lead",
    "лид",
    "crm",
    "support",
    "automation",
    "автоматиза",
    "operator",
    "оператор",
    "sla",
)
ANTI_TERMS = (
    "hype",
    "хайп",
    "failed",
    "не взлет",
    "закрыл",
    "unprofitable",
    "не окуп",
    "no demand",
    "нет спроса",
    "cac exceeds ltv",
)
SEGMENT_TERMS = (
    "founder",
    "фаундер",
    "small business",
    "малый бизнес",
    "enterprise",
    "b2b",
    "agency",
    "агентств",
    "creator",
    "создател",
    "sales",
    "support",
    "c-level",
)


def build_market_pain_pack(
    connection: sqlite3.Connection,
    *,
    cutoff: str,
    limit: int = 120,
    channels: Iterable[str] = MARKET_BUSINESS_CHANNELS,
) -> dict:
    normalized_channels = sorted({_normalize_channel(channel) for channel in channels if channel})
    bounded_limit = max(1, min(int(limit or 120), 300))
    atoms = _fetch_market_atoms(
        connection,
        cutoff=cutoff,
        limit=bounded_limit,
        normalized_channels=normalized_channels,
    )
    curated_channels = sorted(
        {
            channel
            for atom in atoms
            for channel in atom.get("source_channels", [])
            if channel in normalized_channels
        }
    )
    fallback_channels = [channel for channel in normalized_channels if channel not in curated_channels]
    raw_posts = _fetch_market_posts(
        connection,
        cutoff=cutoff,
        limit=max(20, min(bounded_limit, 80)),
        normalized_channels=fallback_channels,
    )
    threads = _fetch_market_threads(
        connection,
        cutoff=cutoff,
        limit=max(8, min(24, bounded_limit // 4)),
        normalized_channels=normalized_channels,
    )
    analyst_context = _build_analyst_context(atoms=atoms, threads=threads, raw_posts=raw_posts)
    status = "available" if atoms or threads or raw_posts else "empty"
    pack = {
        "schema_version": "market_analyst_context.v1",
        "status": status,
        "bounded": True,
        "cutoff": cutoff,
        "channels_requested": [f"@{channel}" for channel in normalized_channels],
        "channels_with_curated_atoms": [f"@{channel}" for channel in curated_channels],
        "channels_using_raw_fallback": [f"@{channel}" for channel in fallback_channels],
        "curated_atom_types": list(MARKET_CONTEXT_ATOM_TYPES),
        "curated_atom_count": len(atoms),
        "market_thread_count": len(threads),
        "raw_fallback_posts_scanned": len(raw_posts),
        "posts_scanned": len(raw_posts),
        "source_refs": _source_refs(atoms=atoms, raw_posts=raw_posts, limit=18),
        "market_threads": threads[:12],
        "curated_atoms": [_public_atom(atom) for atom in atoms[:24]],
        "raw_fallback_observations": [_raw_observation(post, "raw_fallback") for post in raw_posts[:12]],
        "analyst_context": analyst_context,
        # Compatibility fields for existing operator summaries/tests.
        "repeated_pains": analyst_context["market_pains"],
        "icp_customer_types": analyst_context["customer_segments"],
        "urgency_willingness_to_pay_hints": analyst_context["buying_triggers"],
        "distribution_channel_hints": analyst_context["distribution_channels"],
        "workflow_business_model_opportunities": analyst_context["workflow_opportunities"],
        "anti_signals_hype_warnings": analyst_context["what_does_not_work"],
    }
    pack["radar_gate_audit"] = _radar_gate_audit(pack)
    return pack


def market_pack_context_seed(pack: dict) -> dict[str, object] | None:
    if not pack or pack.get("status") != "available":
        return None
    if not _pack_has_observations(pack):
        return None
    text = _pack_text(pack)
    if not text:
        return None
    source_refs = pack.get("source_refs") or []
    first_ref = source_refs[0] if source_refs else {}
    return {
        "upstream_id": f"market-analyst-context:{_date_slug(str(pack.get('cutoff') or 'bounded'))}",
        "captured_at": _pack_captured_at(pack, first_ref),
        "title": "Context Only: Market Analyst Notes",
        "text": text,
        "snippet": _truncate(text, 260),
        "source_url": str(first_ref.get("source_url") or "") if isinstance(first_ref, dict) else "",
        "source_urls": [
            str(ref.get("source_url") or "")
            for ref in source_refs
            if isinstance(ref, dict) and ref.get("source_url")
        ],
        "channel_username": ",".join(
            sorted({str(ref.get("channel") or "") for ref in source_refs if isinstance(ref, dict)})
        ),
        "post_id": "",
        "bucket": "market_context",
        "signal_score": None,
        "user_adjusted_score": None,
        "manual_tags": [],
        "project_names": [],
        "demand_surfaces": [],
        "evidence_strength": "context_only_market_analyst_pack",
        "pain_statement": "Business analyst context only; use to critique candidate plausibility.",
        "target_user": _first_observation_text(pack.get("icp_customer_types") or []) or "Market-aware operators",
        "verification_needed": [
            "do not select this context row as an MVP candidate",
            "external demand validation for any derived candidate",
            "willingness-to-pay evidence outside Telegram",
            "non-Telegram source corroboration",
        ],
        "anti_complexity_note": (
            "Context only. Do not treat Telegram-only market commentary or curated atoms "
            "as build-ready proof."
        ),
        "private": False,
        "source_kind": "market_analyst_context",
        "radar_role": "context_only",
        "build_ready_evidence": False,
        "context_only": True,
        "market_pain_pack": pack,
    }


def summarize_market_pain_pack(pack: dict | None) -> str:
    if not pack:
        return "Market pack: not built."
    status = pack.get("status") or "unknown"
    audit = pack.get("radar_gate_audit") or {}
    if status != "available":
        return f"Market pack: empty bounded lookback; {audit.get('summary') or 'no market context found'}"
    context = pack.get("analyst_context") or {}
    return (
        "Market pack: "
        f"atoms={int(pack.get('curated_atom_count') or 0)}, "
        f"threads={int(pack.get('market_thread_count') or 0)}, "
        f"raw_fallback={int(pack.get('raw_fallback_posts_scanned') or 0)}, "
        f"works={len(context.get('what_works') or [])}, "
        f"risks={len(context.get('what_does_not_work') or [])}; "
        f"{audit.get('summary') or 'context only'}"
    )


def _fetch_market_atoms(
    connection: sqlite3.Connection,
    *,
    cutoff: str,
    limit: int,
    normalized_channels: list[str],
) -> list[dict]:
    if not normalized_channels or not _table_exists(connection, "knowledge_atoms"):
        return []
    atom_placeholders = ",".join("?" for _ in MARKET_CONTEXT_ATOM_TYPES)
    channel_clause, channel_params = _source_url_channel_clause("source_urls_json", normalized_channels)
    rows = connection.execute(
        f"""
        SELECT *
        FROM knowledge_atoms
        WHERE last_seen_at >= ?
          AND atom_type IN ({atom_placeholders})
          AND ({channel_clause})
        ORDER BY practical_utility_score DESC, confidence DESC, last_seen_at DESC, id DESC
        LIMIT ?
        """,
        (cutoff, *MARKET_CONTEXT_ATOM_TYPES, *channel_params, limit),
    ).fetchall()
    return [_row_to_atom(row, normalized_channels) for row in rows]


def _fetch_market_threads(
    connection: sqlite3.Connection,
    *,
    cutoff: str,
    limit: int,
    normalized_channels: list[str],
) -> list[dict]:
    required_tables = ("idea_threads", "idea_thread_atoms", "knowledge_atoms")
    if not normalized_channels or any(not _table_exists(connection, table) for table in required_tables):
        return []
    atom_placeholders = ",".join("?" for _ in MARKET_CONTEXT_ATOM_TYPES)
    channel_clause, channel_params = _source_url_channel_clause("knowledge_atoms.source_urls_json", normalized_channels)
    rows = connection.execute(
        f"""
        SELECT DISTINCT
            idea_threads.id,
            idea_threads.title,
            idea_threads.slug,
            idea_threads.summary,
            idea_threads.status,
            idea_threads.first_seen_at,
            idea_threads.last_seen_at,
            idea_threads.momentum_30d,
            idea_threads.momentum_90d,
            idea_threads.atom_count,
            idea_threads.source_channel_count,
            idea_threads.source_channels_json,
            idea_threads.key_entities_json,
            idea_threads.current_claims_json
        FROM idea_threads
        JOIN idea_thread_atoms ON idea_thread_atoms.thread_id = idea_threads.id
        JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
        WHERE idea_threads.last_seen_at >= ?
          AND knowledge_atoms.last_seen_at >= ?
          AND knowledge_atoms.atom_type IN ({atom_placeholders})
          AND ({channel_clause})
        ORDER BY
            idea_threads.momentum_30d DESC,
            idea_threads.last_seen_at DESC,
            idea_threads.atom_count DESC,
            idea_threads.title ASC
        LIMIT ?
        """,
        (cutoff, cutoff, *MARKET_CONTEXT_ATOM_TYPES, *channel_params, limit),
    ).fetchall()
    return [_row_to_thread(row) for row in rows]


def _fetch_market_posts(
    connection: sqlite3.Connection,
    *,
    cutoff: str,
    limit: int,
    normalized_channels: list[str],
) -> list[dict]:
    if not normalized_channels or not _table_exists(connection, "posts") or not _table_exists(connection, "raw_posts"):
        return []
    placeholders = ",".join("?" for _ in normalized_channels)
    rows = connection.execute(
        f"""
        SELECT
            p.id AS post_id,
            p.channel_username,
            p.posted_at,
            p.content,
            p.bucket,
            p.signal_score,
            r.message_id,
            r.message_url,
            r.view_count
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.posted_at >= ?
          AND lower(replace(p.channel_username, '@', '')) IN ({placeholders})
        ORDER BY p.posted_at DESC, p.id DESC
        LIMIT ?
        """,
        (cutoff, *normalized_channels, limit),
    ).fetchall()
    return [_row_to_post(row) for row in rows]


def _build_analyst_context(*, atoms: list[dict], threads: list[dict], raw_posts: list[dict]) -> dict:
    context = {
        "role": "business analyst context for MVP Radar; not a candidate list",
        "what_works": [],
        "what_does_not_work": [],
        "market_pains": [],
        "buying_triggers": [],
        "customer_segments": [],
        "distribution_channels": [],
        "workflow_opportunities": [],
        "proof_points": [],
        "open_questions": [
            "Which non-Telegram public sources confirm the same pain?",
            "Where is willingness-to-pay visible outside commentary?",
            "Which candidate can be validated without becoming a broad platform?",
        ],
        "thread_context": [
            {
                "title": thread.get("title"),
                "summary": thread.get("summary"),
                "status": thread.get("status"),
                "last_seen_at": thread.get("last_seen_at"),
                "source_channels": thread.get("source_channels") or [],
            }
            for thread in threads[:8]
        ],
    }
    for atom in atoms:
        text = _atom_text(atom)
        if atom.get("atom_type") in {"case_study", "workflow_pattern", "market_signal"}:
            _append_observation(context["what_works"], _atom_observation(atom, "what_works"))
        if atom.get("atom_type") == "risk_warning" or _has_any(text, ANTI_TERMS):
            _append_observation(context["what_does_not_work"], _atom_observation(atom, "what_does_not_work"))
        if atom.get("atom_type") in {"market_signal", "workflow_pattern"} or _has_any(text, PAIN_TERMS):
            _append_observation(context["market_pains"], _atom_observation(atom, "market_pain"))
        if _has_any(text, BUYING_TERMS):
            _append_observation(context["buying_triggers"], _atom_observation(atom, "buying_trigger"))
        if _has_any(text, DISTRIBUTION_TERMS):
            _append_observation(context["distribution_channels"], _atom_observation(atom, "distribution_channel"))
        if atom.get("atom_type") == "workflow_pattern" or _has_any(text, WORKFLOW_TERMS):
            _append_observation(context["workflow_opportunities"], _atom_observation(atom, "workflow_opportunity"))
        if atom.get("atom_type") == "case_study" or _looks_like_proof_point(text):
            _append_observation(context["proof_points"], _atom_observation(atom, "proof_point"))
        for segment in _segments_from_atom(atom):
            _append_observation(context["customer_segments"], segment)
    for post in raw_posts:
        text = str(post.get("content") or "")
        if _has_any(text, ANTI_TERMS):
            _append_observation(context["what_does_not_work"], _raw_observation(post, "what_does_not_work"))
        if _has_any(text, PAIN_TERMS):
            _append_observation(context["market_pains"], _raw_observation(post, "market_pain"))
        if _has_any(text, BUYING_TERMS):
            _append_observation(context["buying_triggers"], _raw_observation(post, "buying_trigger"))
        if _has_any(text, DISTRIBUTION_TERMS):
            _append_observation(context["distribution_channels"], _raw_observation(post, "distribution_channel"))
        if _has_any(text, WORKFLOW_TERMS):
            _append_observation(context["workflow_opportunities"], _raw_observation(post, "workflow_opportunity"))
        if _has_any(text, SEGMENT_TERMS):
            _append_observation(context["customer_segments"], _raw_observation(post, "customer_segment"))
    for key in (
        "what_works",
        "what_does_not_work",
        "market_pains",
        "buying_triggers",
        "customer_segments",
        "distribution_channels",
        "workflow_opportunities",
        "proof_points",
    ):
        context[key] = context[key][:8]
    return context


def _row_to_atom(row: sqlite3.Row, normalized_channels: list[str]) -> dict:
    source_urls = _parse_array(row["source_urls_json"])
    source_channels = sorted(
        {
            channel
            for url in source_urls
            for channel in [_source_channel(url)]
            if channel and channel in normalized_channels
        }
    )
    return {
        "id": int(row["id"]),
        "atom_type": str(row["atom_type"] or ""),
        "claim": str(row["claim"] or ""),
        "summary": str(row["summary"] or ""),
        "evidence_quote": str(row["evidence_quote"] or ""),
        "source_urls": source_urls,
        "source_channels": source_channels,
        "entities": _parse_array(row["entities_json"]),
        "tools": _parse_array(row["tools_json"]),
        "practices": _parse_array(row["practices_json"]),
        "confidence": float(row["confidence"] or 0.0),
        "practical_utility_score": float(row["practical_utility_score"] or 0.0),
        "last_seen_at": str(row["last_seen_at"] or ""),
    }


def _row_to_thread(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "title": str(row["title"] or ""),
        "slug": str(row["slug"] or ""),
        "summary": str(row["summary"] or ""),
        "status": str(row["status"] or ""),
        "first_seen_at": str(row["first_seen_at"] or ""),
        "last_seen_at": str(row["last_seen_at"] or ""),
        "momentum_30d": float(row["momentum_30d"] or 0.0),
        "momentum_90d": float(row["momentum_90d"] or 0.0),
        "atom_count": int(row["atom_count"] or 0),
        "source_channel_count": int(row["source_channel_count"] or 0),
        "source_channels": _parse_array(row["source_channels_json"]),
        "key_entities": _parse_array(row["key_entities_json"]),
        "current_claims": _parse_array(row["current_claims_json"]),
    }


def _row_to_post(row: sqlite3.Row) -> dict:
    channel = str(row["channel_username"] or "")
    message_id = int(row["message_id"] or 0)
    source_url = str(row["message_url"] or "").strip() or _message_url(channel, message_id)
    return {
        "post_id": int(row["post_id"]),
        "channel": channel,
        "posted_at": str(row["posted_at"] or ""),
        "content": " ".join(str(row["content"] or "").split()),
        "bucket": str(row["bucket"] or ""),
        "signal_score": row["signal_score"],
        "message_id": message_id,
        "source_url": source_url,
        "view_count": row["view_count"],
    }


def _source_refs(*, atoms: list[dict], raw_posts: list[dict], limit: int) -> list[dict]:
    refs = []
    for atom in atoms:
        for url in atom.get("source_urls") or []:
            refs.append(
                {
                    "source_kind": "knowledge_atom",
                    "atom_id": atom.get("id"),
                    "atom_type": atom.get("atom_type"),
                    "channel": f"@{_source_channel(url)}" if _source_channel(url) else "",
                    "source_url": url,
                    "posted_at": atom.get("last_seen_at"),
                }
            )
    for post in raw_posts:
        refs.append(
            {
                "source_kind": "raw_post_fallback",
                "channel": post.get("channel"),
                "source_url": post.get("source_url"),
                "posted_at": post.get("posted_at"),
                "bucket": post.get("bucket"),
            }
        )
    return _dedupe_refs(refs)[:limit]


def _public_atom(atom: dict) -> dict:
    return {
        "id": atom.get("id"),
        "atom_type": atom.get("atom_type"),
        "claim": atom.get("claim"),
        "summary": atom.get("summary"),
        "evidence_quote": atom.get("evidence_quote"),
        "source_urls": atom.get("source_urls") or [],
        "source_channels": [f"@{channel}" for channel in atom.get("source_channels", [])],
        "confidence": atom.get("confidence"),
        "practical_utility_score": atom.get("practical_utility_score"),
        "last_seen_at": atom.get("last_seen_at"),
    }


def _radar_gate_audit(pack: dict) -> dict:
    if pack.get("status") != "available":
        return {
            "status": "no_market_context",
            "context_only": True,
            "build_ready_evidence": False,
            "summary": "no market/business atoms or fallback posts found in bounded lookback",
            "missing_evidence": [
                "recent market-channel posts or curated atoms",
                "external demand validation",
                "willingness-to-pay signal",
            ],
        }
    missing = [
        "external demand validation for any derived candidate",
        "willingness-to-pay evidence outside Telegram",
        "second independent non-Telegram source type",
    ]
    if not (pack.get("analyst_context") or {}).get("buying_triggers"):
        missing.insert(0, "pricing or budget signal")
    return {
        "status": "context_only",
        "context_only": True,
        "build_ready_evidence": False,
        "summary": "market analyst pack is context only; Radar must keep external evidence gates",
        "missing_evidence": missing,
    }


def _pack_text(pack: dict) -> str:
    context = pack.get("analyst_context") or {}
    lines = [
        "Business analyst context for MVP Radar.",
        "Context only: do not select this row as an MVP candidate and do not treat it as build-ready proof.",
        f"Channels: {', '.join(pack.get('channels_requested') or [])}",
        (
            "Curated inputs: "
            f"{pack.get('curated_atom_count') or 0} atoms, "
            f"{pack.get('market_thread_count') or 0} threads, "
            f"{pack.get('raw_fallback_posts_scanned') or 0} raw fallback posts."
        ),
    ]
    sections = (
        ("What seems to work", "what_works"),
        ("What seems not to work / risks", "what_does_not_work"),
        ("Market pains", "market_pains"),
        ("Buying triggers / WTP hints", "buying_triggers"),
        ("Customer segments", "customer_segments"),
        ("Distribution channels", "distribution_channels"),
        ("Workflow opportunities", "workflow_opportunities"),
        ("Proof points", "proof_points"),
    )
    for title, key in sections:
        items = context.get(key) or []
        if not items:
            continue
        lines.append(title + ":")
        for item in items[:5]:
            lines.append(f"- {item.get('text')} ({item.get('source_url') or 'no source URL'})")
    if context.get("thread_context"):
        lines.append("Relevant idea threads:")
        for thread in context.get("thread_context", [])[:5]:
            lines.append(
                f"- {thread.get('title')}: {_truncate(str(thread.get('summary') or ''), 180)}"
            )
    return "\n".join(lines)


def _pack_has_observations(pack: dict) -> bool:
    context = pack.get("analyst_context") or {}
    keys = [
        "what_works",
        "what_does_not_work",
        "market_pains",
        "buying_triggers",
        "workflow_opportunities",
        "proof_points",
    ]
    if int(pack.get("curated_atom_count") or 0) or int(pack.get("market_thread_count") or 0):
        keys.extend(["customer_segments", "distribution_channels"])
    for key in keys:
        if context.get(key):
            return True
    return bool(pack.get("market_threads")) and (
        int(pack.get("curated_atom_count") or 0) > 0
        or int(pack.get("market_thread_count") or 0) > 0
    )


def _atom_observation(atom: dict, category: str) -> dict:
    quote = str(atom.get("evidence_quote") or "").strip()
    text = str(atom.get("claim") or atom.get("summary") or quote).strip()
    if quote and quote.lower() not in text.lower():
        text = f"{text} Evidence: {quote}"
    source_url = _first(atom.get("source_urls") or [])
    source_channel = _source_channel(source_url)
    return {
        "category": category,
        "text": _truncate(text, 260),
        "source_url": source_url,
        "channel": f"@{source_channel}" if source_channel else "",
        "atom_id": atom.get("id"),
        "atom_type": atom.get("atom_type"),
        "confidence": atom.get("confidence"),
        "practical_utility_score": atom.get("practical_utility_score"),
        "last_seen_at": atom.get("last_seen_at"),
    }


def _raw_observation(post: dict, category: str) -> dict:
    return {
        "category": category,
        "text": _truncate(_first_sentence(str(post.get("content") or "")), 240),
        "source_url": post.get("source_url"),
        "channel": post.get("channel"),
        "bucket": post.get("bucket"),
        "posted_at": post.get("posted_at"),
    }


def _segments_from_atom(atom: dict) -> list[dict]:
    results = []
    text = _atom_text(atom)
    source = _atom_observation(atom, "customer_segment")
    for entity in atom.get("entities") or []:
        entity_text = str(entity or "").strip()
        if not entity_text:
            continue
        if _has_any(entity_text, SEGMENT_TERMS):
            item = dict(source)
            item["text"] = entity_text
            results.append(item)
    if not results and _has_any(text, SEGMENT_TERMS):
        results.append(source)
    return results


def _append_observation(items: list[dict], item: dict) -> None:
    key = (str(item.get("category") or ""), str(item.get("text") or ""), str(item.get("source_url") or ""))
    for existing in items:
        existing_key = (
            str(existing.get("category") or ""),
            str(existing.get("text") or ""),
            str(existing.get("source_url") or ""),
        )
        if existing_key == key:
            return
    items.append(item)


def _source_url_channel_clause(column: str, normalized_channels: list[str]) -> tuple[str, list[str]]:
    parts = [f"lower({column}) LIKE ?" for _ in normalized_channels]
    params = [f"%t.me/{channel.lower()}/%" for channel in normalized_channels]
    return " OR ".join(parts) or "0", params


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_array(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _atom_text(atom: dict) -> str:
    parts = [
        atom.get("claim"),
        atom.get("summary"),
        atom.get("evidence_quote"),
        " ".join(str(item) for item in atom.get("entities") or []),
        " ".join(str(item) for item in atom.get("tools") or []),
        " ".join(str(item) for item in atom.get("practices") or []),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _looks_like_proof_point(text: str) -> bool:
    return bool(re.search(r"(\d+[%$]|\$\d+|\d+\s*(demo|демо|users|conversions|mrr|arr))", text.lower()))


def _has_any(text: str, terms: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(term).lower() in lowered for term in terms if str(term).strip())


def _dedupe_refs(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = str(item.get("source_url") or item.get("atom_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _first_observation_text(items: list[dict]) -> str:
    if not items:
        return ""
    return str(items[0].get("text") or "")


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


def _message_url(channel: str, message_id: int) -> str:
    username = channel.strip().lstrip("@")
    if not username or message_id <= 0:
        return ""
    return f"https://t.me/{username}/{message_id}"


def _source_channel(url: str) -> str:
    match = re.search(r"t\.me/([^/?#]+)", str(url or ""), re.IGNORECASE)
    return _normalize_channel(match.group(1)) if match else ""


def _normalize_channel(channel: str) -> str:
    return channel.strip().lower().lstrip("@")


def _date_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-") or "bounded"


def _truncate(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 3)].rstrip() + "..."


def _pack_captured_at(pack: dict, first_ref: object) -> str:
    if isinstance(first_ref, dict) and first_ref.get("posted_at"):
        return str(first_ref.get("posted_at"))
    return str(pack.get("cutoff") or "")


def _first(values: list) -> str:
    if not values:
        return ""
    return str(values[0] or "")
