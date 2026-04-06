"""
Insight Triage Layer.

Classifies raw LLM-generated insights into do_now / backlog / reject_or_defer.
Applies rejection memory to suppress repeated low-value ideas.
All classification logic is deterministic — no additional LLM calls.
"""
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


REJECTION_MEMORY_WEEKS = 4  # reject_or_defer items suppressed for this many weeks

_CATEGORY_LABELS: dict[str, str] = {
    "do_now": "✅ Сделать сейчас",
    "backlog": "📋 Бэклог",
    "reject_or_defer": "⏸ Отложить / отклонить",
}
_CATEGORY_ORDER = ["do_now", "backlog", "reject_or_defer"]


@dataclass
class TriagedInsight:
    title: str
    summary: str
    source_url: str
    idea_type: str          # "implement" | "build" | "unknown"
    timing: str             # "now" | "quarter" | "later"
    implementation_mode: str  # "extend" | "extract" | "rebuild" | "new"
    confidence: str         # "high" | "medium" | "low"
    evidence_strength: str  # "strong" | "moderate" | "weak"
    main_risk: str
    recommendation: str     # "do_now" | "backlog" | "reject_or_defer"
    reason: str
    suppressed: bool = False
    source_html: str = ""   # original HTML block for rendering


def _normalize_fingerprint(title: str) -> str:
    """Stable fingerprint for rejection memory lookup."""
    normalized = unicodedata.normalize("NFKD", title.lower())
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    tokens = sorted(normalized.split())
    return " ".join(tokens)


def _detect_idea_type(header: str) -> str:
    lower = header.lower()
    if "[implement]" in lower:
        return "implement"
    if "[build]" in lower:
        return "build"
    return "unknown"


def _detect_implementation_mode(title: str, body: str) -> str:
    text = (title + " " + body).lower()
    if any(w in text for w in ("rebuild", "rewrite", "переписать", "полностью переделать")):
        return "rebuild"
    if any(w in text for w in ("extract", "вынести", "выделить", "отделить")):
        return "extract"
    if any(w in text for w in ("create new", "новый инструмент", "новый проект", "build new")):
        return "new"
    return "extend"


def _is_speculative(title: str, body: str, idea_type: str) -> bool:
    """Heuristic: is this idea portfolio-candy or weakly grounded?"""
    text = (title + " " + body).lower()
    speculative_signals = [
        "portfolio",
        "портфолио",
        "showcase",
        "generic framework",
        "универсальный фреймворк",
        "completely rewrite",
        "полностью переписать",
    ]
    if idea_type == "build" and any(s in text for s in speculative_signals):
        return True
    return False


def parse_insights_html(html_text: str) -> list[tuple[str, str, str, str]]:
    """
    Parse insights HTML into list of (header, body_text, source_url, raw_html_block) tuples.

    Expects LLM output in the format:
        <b>[Implement] ProjectName — Idea Title</b>
        Body text
        <a href="url">источник</a>

    Returns empty list if no recognisable idea headers are found.
    """
    pattern = re.compile(r"<b>(\[(?:Implement|Build)\][^<]*)</b>", re.IGNORECASE)
    matches = list(pattern.finditer(html_text))
    results: list[tuple[str, str, str, str]] = []
    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_text)
        raw_block = html_text[match.start():end].strip()
        section = html_text[start:end]
        url_match = re.search(r'<a\s+href="([^"]+)"', section)
        source_url = url_match.group(1) if url_match else ""
        body = re.sub(r"<[^>]+>", " ", section)
        body = re.sub(r"\s+", " ", body).strip()
        results.append((header, body, source_url, raw_block))
    return results


def classify_insight(
    header: str,
    body: str,
    source_url: str,
    *,
    raw_html: str = "",
    rejection_fingerprints: set[str] | None = None,
) -> TriagedInsight:
    """Classify a single insight. Fully deterministic, no LLM calls."""
    idea_type = _detect_idea_type(header)
    impl_mode = _detect_implementation_mode(header, body)

    timing = "now" if idea_type == "implement" else "quarter"
    evidence = "strong" if idea_type == "implement" else "moderate"
    confidence = "high" if idea_type == "implement" else "medium"

    _risk_map: dict[str, str] = {
        "rebuild": "High scope: full rewrites often exceed budget and break existing behaviour",
        "extract": "Moderate: extraction can introduce hidden coupling",
        "extend": "Low: adding to existing surface without structural change",
        "new": "Distraction risk: new projects compete with current focus",
    }
    main_risk = _risk_map.get(impl_mode, "Unknown risk")

    fingerprint = _normalize_fingerprint(header)

    if rejection_fingerprints and fingerprint in rejection_fingerprints:
        return TriagedInsight(
            title=header,
            summary=body,
            source_url=source_url,
            idea_type=idea_type,
            timing=timing,
            implementation_mode=impl_mode,
            confidence=confidence,
            evidence_strength=evidence,
            main_risk=main_risk,
            recommendation="reject_or_defer",
            reason="Previously rejected — not yet eligible for revisit",
            suppressed=True,
            source_html=raw_html,
        )

    speculative = _is_speculative(header, body, idea_type)

    if impl_mode == "rebuild" or speculative:
        recommendation = "reject_or_defer"
        reason = "Rebuild or speculative abstraction — high cost, evidence-weak return"
    elif idea_type == "implement":
        recommendation = "do_now"
        reason = "Direct improvement to existing project with cited evidence"
    elif idea_type == "build":
        recommendation = "backlog"
        reason = "New project concept — useful but not urgent for current work horizon"
    else:
        recommendation = "backlog"
        reason = "Type unknown — needs manual review before scheduling"

    return TriagedInsight(
        title=header,
        summary=body,
        source_url=source_url,
        idea_type=idea_type,
        timing=timing,
        implementation_mode=impl_mode,
        confidence=confidence,
        evidence_strength=evidence,
        main_risk=main_risk,
        recommendation=recommendation,
        reason=reason,
        suppressed=False,
        source_html=raw_html,
    )


def load_rejection_fingerprints(connection: sqlite3.Connection) -> set[str]:
    """Load active rejection memory fingerprints (within REJECTION_MEMORY_WEEKS)."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(weeks=REJECTION_MEMORY_WEEKS)
    ).isoformat().replace("+00:00", "Z")
    rows = connection.execute(
        """
        SELECT title_fingerprint
        FROM insight_rejection_memory
        WHERE rejected_at >= ?
        """,
        (cutoff,),
    ).fetchall()
    return {row[0] for row in rows}


def store_triage_results(
    connection: sqlite3.Connection,
    week_label: str,
    insights: list[TriagedInsight],
) -> None:
    """Persist triage results. Clears existing records for this week first (idempotent)."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    connection.execute(
        "DELETE FROM insight_triage_records WHERE week_label = ?",
        (week_label,),
    )
    for insight in insights:
        connection.execute(
            """
            INSERT INTO insight_triage_records
                (week_label, title, idea_type, timing, implementation_mode,
                 confidence, evidence_strength, main_risk, recommendation, reason,
                 source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                week_label,
                insight.title,
                insight.idea_type,
                insight.timing,
                insight.implementation_mode,
                insight.confidence,
                insight.evidence_strength,
                insight.main_risk,
                insight.recommendation,
                insight.reason,
                insight.source_url,
                now_iso,
            ),
        )


def update_rejection_memory(
    connection: sqlite3.Connection,
    insights: list[TriagedInsight],
) -> None:
    """Record new reject_or_defer items in rejection memory. Upserts by fingerprint."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for insight in insights:
        if insight.recommendation != "reject_or_defer":
            continue
        fingerprint = _normalize_fingerprint(insight.title)
        connection.execute(
            """
            INSERT INTO insight_rejection_memory
                (title_fingerprint, title, reason, rejected_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(title_fingerprint) DO UPDATE SET
                rejected_at = excluded.rejected_at,
                reason = excluded.reason
            """,
            (fingerprint, insight.title, insight.reason, now_iso),
        )


def triage_insights(
    html_text: str,
    connection: sqlite3.Connection,
    week_label: str,
) -> list[TriagedInsight]:
    """
    Full triage pipeline: parse → load rejection memory → classify → store.
    Returns list of TriagedInsight (including suppressed items).
    """
    rejection_fingerprints = load_rejection_fingerprints(connection)
    parsed = parse_insights_html(html_text)

    insights: list[TriagedInsight] = []
    for header, body, source_url, raw_html in parsed:
        insight = classify_insight(
            header,
            body,
            source_url,
            raw_html=raw_html,
            rejection_fingerprints=rejection_fingerprints,
        )
        insights.append(insight)

    store_triage_results(connection, week_label, insights)
    update_rejection_memory(connection, insights)

    return insights


def render_triaged_insights_html(
    raw_html: str,
    insights: list[TriagedInsight],
) -> str:
    """
    Render insights HTML with triage labels, grouping do_now → backlog → reject_or_defer.
    Falls back to raw_html if no ideas were parsed.
    """
    if not insights:
        return raw_html

    by_category: dict[str, list[TriagedInsight]] = {cat: [] for cat in _CATEGORY_ORDER}
    for insight in insights:
        cat = insight.recommendation if insight.recommendation in by_category else "backlog"
        by_category[cat].append(insight)

    blocks: list[str] = ["<b>💡 Инсайты недели</b>"]

    for category in _CATEGORY_ORDER:
        items = by_category[category]
        if not items:
            continue
        label = _CATEGORY_LABELS[category]
        blocks.append(f"<b>{label}</b>")
        for item in items:
            if item.source_html:
                triage_note = f"<i>({item.reason})</i>"
                blocks.append(f"{item.source_html}\n{triage_note}")
            else:
                blocks.append(
                    f"<b>{item.title}</b>\n{item.summary}\n<i>({item.reason})</i>"
                )

    return "\n\n".join(blocks)
