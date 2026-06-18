import logging
import os
import re
import sqlite3
import html
from datetime import timezone, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from bot.callbacks import build_artifact_feedback_markup, build_idea_feedback_markup
from db.retrieval import fetch_decisions, fetch_evidence_items
from config.settings import PROJECT_ROOT, Settings
from bot.telegram_delivery import send_document, send_text
from delivery.telegraph import publish_article
from llm.client import complete
from output.context_memory import load_project_context, refresh_all_project_context_snapshots
from output.insight_triage import parse_insights_html, render_triaged_insights_html, triage_insights
from output.report_utils import _extract_markdown_section
from output.weekly_messages import (
    build_implementation_message,
    build_project_freshness_blocked_message,
    write_weekly_message,
)

try:
    from integrations.github_sync import sync_github_projects
except Exception:  # pragma: no cover - import must not block offline recommendation tests
    sync_github_projects = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "insights.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "recommendations"
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"
PROJECT_CONTEXT_MAX_SYNC_AGE_DAYS = 2
INLINE_URL_RE = re.compile(r"(?<![\"'>])(https?://[^\s<]+)")
TELEGRAM_URL_RE = re.compile(r"https?://t\.me/[A-Za-z0-9_]+/\d+(?:\?[^\s<]+)?", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ANCHOR_RE = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
INSIGHT_SECTION_HEADINGS = {
    "🧱 собранные идеи",
    "🆕 отдельные сигналы",
    "built ideas",
    "fresh signals",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
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


def _load_prompt_sections() -> tuple[str, str]:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = _extract_markdown_section(prompt_markdown, "System Prompt")
    user_template = _extract_markdown_section(prompt_markdown, "User Prompt Template")
    return system_prompt, user_template


def _load_projects_context() -> str:
    data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    lines = []
    for project in projects:
        name = project.get("name", "")
        description = project.get("description", "")
        focus = project.get("focus", "")
        lines.append(f"{name}: {description}. Фокус: {focus}")
    return "\n".join(lines)


def _load_project_names() -> list[str]:
    data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8"))
    return [str(p.get("name", "")).strip() for p in data.get("projects", []) if p.get("name")]


def _load_project_repos() -> list[str]:
    data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8"))
    repos: list[str] = []
    for project in data.get("projects", []):
        repo = str(project.get("repo") or "").strip()
        if repo:
            repos.append(repo)
    return repos


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _maybe_sync_project_context(db_path: str) -> dict[str, Any]:
    if not os.environ.get("GITHUB_TOKEN"):
        return {
            "attempted": False,
            "repos_synced": 0,
            "error": "",
            "reason": "GITHUB_TOKEN is not set",
        }
    if sync_github_projects is None:
        return {
            "attempted": False,
            "repos_synced": 0,
            "error": "",
            "reason": "GitHub sync integration is unavailable",
        }
    try:
        synced = sync_github_projects(db_path)
        return {
            "attempted": True,
            "repos_synced": len(synced),
            "error": "",
            "reason": "",
        }
    except Exception as exc:
        LOGGER.warning("Fresh project context sync failed", exc_info=True)
        return {
            "attempted": True,
            "repos_synced": 0,
            "error": str(exc),
            "reason": "GitHub sync raised an exception",
        }


def _load_project_freshness_rows(connection: sqlite3.Connection, repos: list[str]) -> list[dict[str, str]]:
    if not repos:
        return []
    placeholders = ",".join("?" for _ in repos)
    rows = connection.execute(
        f"""
        SELECT
            projects.name,
            projects.github_repo,
            projects.github_synced_at,
            projects.last_commit_at,
            project_context_snapshots.source_commit_at,
            project_context_snapshots.updated_at AS snapshot_updated_at,
            project_context_snapshots.recent_changes
        FROM projects
        LEFT JOIN project_context_snapshots
          ON project_context_snapshots.project_id = projects.id
        WHERE projects.github_repo IN ({placeholders})
           OR projects.name IN ({placeholders})
        """,
        repos + repos,
    ).fetchall()
    return [
        {
            "name": str(row["name"] or ""),
            "github_repo": str(row["github_repo"] or ""),
            "github_synced_at": str(row["github_synced_at"] or ""),
            "last_commit_at": str(row["last_commit_at"] or ""),
            "source_commit_at": str(row["source_commit_at"] or ""),
            "snapshot_updated_at": str(row["snapshot_updated_at"] or ""),
            "recent_changes": str(row["recent_changes"] or ""),
        }
        for row in rows
    ]


def _build_project_freshness_report(
    connection: sqlite3.Connection,
    *,
    sync_result: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    repos = _load_project_repos()
    try:
        rows = _load_project_freshness_rows(connection, repos)
    except sqlite3.Error:
        LOGGER.warning("Failed to load project freshness rows", exc_info=True)
        return {
            "gate_passed": True,
            "sync_attempted": bool(sync_result.get("attempted")),
            "repos_synced": int(sync_result.get("repos_synced") or 0),
            "latest_github_synced_at": "",
            "blocking_reasons": [],
            "stale_projects": [],
            "prompt_context": "Project freshness unavailable; do not infer repo recency.",
        }

    rows_by_repo = {
        (row.get("github_repo") or row.get("name") or "").strip(): row
        for row in rows
        if (row.get("github_repo") or row.get("name") or "").strip()
    }
    missing_repos = [repo for repo in repos if repo not in rows_by_repo]
    stale_projects: list[str] = []
    latest_sync_at: datetime | None = None
    latest_sync_raw = ""
    blocking_reasons: list[str] = []

    for repo in repos:
        row = rows_by_repo.get(repo)
        if row is None:
            stale_projects.append(repo)
            continue
        synced_at_raw = row.get("github_synced_at") or ""
        synced_at = _parse_iso_datetime(synced_at_raw)
        if synced_at and (latest_sync_at is None or synced_at > latest_sync_at):
            latest_sync_at = synced_at
            latest_sync_raw = synced_at_raw
        if synced_at is None:
            stale_projects.append(repo)
            continue
        if current - synced_at > timedelta(days=PROJECT_CONTEXT_MAX_SYNC_AGE_DAYS):
            stale_projects.append(repo)

    if sync_result.get("attempted") and int(sync_result.get("repos_synced") or 0) == 0:
        blocking_reasons.append("GitHub sync был запущен, но не обновил ни одного репозитория")
    if sync_result.get("error"):
        blocking_reasons.append(f"GitHub sync error: {sync_result['error']}")
    if missing_repos:
        blocking_reasons.append(f"нет project rows для {len(missing_repos)} curated repos")
    if stale_projects:
        blocking_reasons.append(
            f"{len(stale_projects)} curated repos имеют github_synced_at старше {PROJECT_CONTEXT_MAX_SYNC_AGE_DAYS} дней или пустой sync"
        )

    gate_passed = not blocking_reasons
    recent_change_count = sum(1 for row in rows if row.get("recent_changes"))
    prompt_context = "\n".join(
        [
            f"Project freshness gate: {'passed' if gate_passed else 'blocked'}",
            f"sync_attempted={bool(sync_result.get('attempted'))}",
            f"repos_synced={int(sync_result.get('repos_synced') or 0)}",
            f"latest_github_synced_at={latest_sync_raw or 'n/a'}",
            f"rows_with_recent_changes={recent_change_count}/{len(rows)}",
            f"blocking_reasons={'; '.join(blocking_reasons) if blocking_reasons else 'none'}",
        ]
    )
    return {
        "gate_passed": gate_passed,
        "sync_attempted": bool(sync_result.get("attempted")),
        "repos_synced": int(sync_result.get("repos_synced") or 0),
        "latest_github_synced_at": latest_sync_raw,
        "blocking_reasons": blocking_reasons,
        "stale_projects": stale_projects,
        "prompt_context": prompt_context,
    }


def _load_recent_decisions(connection: sqlite3.Connection) -> str:
    try:
        rows = fetch_decisions(
            connection,
            decision_scope="insight",
            limit=20,
        )
    except Exception:
        LOGGER.warning("Failed to load recent decisions for recommendations", exc_info=True)
        return "No recent decision history available."
    if not rows:
        return "No recent decision history available."
    lines: list[str] = []
    for row in rows:
        status = str(row.get("status") or "")
        reason = str(row.get("reason") or "")[:120]
        ref_id = str(row.get("subject_ref_id") or "")[:80]
        recorded_at = str(row.get("recorded_at") or "")[:10]
        lines.append(f"[{recorded_at}] {ref_id}: {status} — {reason}")
    return "\n".join(lines)


def _tokenize_match_text(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W_]+", (text or "").lower(), flags=re.UNICODE)
        if len(token) >= 4
    }


def _extract_project_name_from_header(header: str) -> str:
    match = re.match(r"\[(?:Implement|Build)\]\s+(.+?)\s+[—–-]\s+", header.strip(), re.IGNORECASE)
    return match.group(1).strip().lower() if match else ""


def _load_recent_project_evidence(connection: sqlite3.Connection) -> tuple[str, list[dict]]:
    project_names = _load_project_names()
    if not project_names:
        return "No project evidence available.", []
    now = _utc_now()
    end_year, end_week, _ = now.isocalendar()
    start_year, start_week, _ = (now - timedelta(weeks=2)).isocalendar()
    week_range = [f"{start_year}-W{start_week:02d}", f"{end_year}-W{end_week:02d}"]
    lines: list[str] = []
    candidates: list[dict] = []
    for name in project_names:
        try:
            items = fetch_evidence_items(connection, project_name=name, week_range=week_range, limit=3)
        except Exception:
            LOGGER.warning("Failed to load evidence for project=%s", name, exc_info=True)
            continue
        for item in items:
            kind = str(item.get("evidence_kind") or "")
            excerpt = str(item.get("excerpt_text") or "")[:220]
            channel = str(item.get("source_channel") or "")
            week = str(item.get("week_label") or "")
            url = str(item.get("message_url") or "").strip()
            line = f"[{name}][{week}][{kind}] {channel}: {excerpt}"
            if url:
                line += f" {url}"
            lines.append(line[:280])
            if url:
                candidates.append(
                    {
                        "url": url,
                        "project_name": name.lower(),
                        "channel": channel.lower(),
                        "match_text": f"{name} {channel} {excerpt}",
                    }
                )
    return ("\n".join(lines) if lines else "No recent project evidence found."), candidates


def _load_project_context_snapshots(connection: sqlite3.Connection) -> str:
    refresh_all_project_context_snapshots(connection)
    snapshots = load_project_context(connection)
    if not snapshots:
        return "No project context snapshots available yet."
    lines: list[str] = []
    for item in snapshots:
        name = str(item.get("project_name") or "")
        summary = str(item.get("summary") or "")
        recent_changes = str(item.get("recent_changes") or "")
        open_questions = str(item.get("open_questions") or "")
        lines.append(f"{name}: {summary}")
        if recent_changes:
            lines.append(f"  recent_changes: {recent_changes}")
        if open_questions:
            lines.append(f"  open_questions: {open_questions}")
    return "\n".join(lines)


def _load_digest_summary(connection: sqlite3.Connection, week_label: str) -> tuple[str | None, str, list[dict]]:
    row = connection.execute(
        """
        SELECT content_md
        FROM digests
        WHERE week_label = ?
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return None, "", []
    digest_md = row["content_md"]

    week_start_iso, week_end_iso = _week_bounds(week_label)
    topic_rows = connection.execute(
        """
        SELECT topics.label, COUNT(*) AS post_count
        FROM post_topics
        INNER JOIN topics ON topics.id = post_topics.topic_id
        INNER JOIN posts ON posts.id = post_topics.post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        GROUP BY topics.id, topics.label
        ORDER BY post_count DESC, topics.label ASC
        LIMIT 10
        """,
        (week_start_iso, week_end_iso),
    ).fetchall()

    notable_rows = connection.execute(
        """
        SELECT
            posts.channel_username,
            posts.content,
            raw_posts.message_url,
            COALESCE(raw_posts.view_count, 0) AS view_count
        FROM posts
        INNER JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        ORDER BY view_count DESC, posts.posted_at DESC
        LIMIT 10
        """,
        (week_start_iso, week_end_iso),
    ).fetchall()

    lines = []
    candidates: list[dict] = []
    if topic_rows:
        lines.append("Топ тем:")
        for row in topic_rows:
            lines.append(f"  - {row['label']} ({row['post_count']} постов)")

    if notable_rows:
        lines.append("\nПримечательные посты:")
        for row in notable_rows:
            excerpt = " ".join((row["content"] or "").split())[:200]
            url = row["message_url"] or ""
            channel = row["channel_username"] or ""
            lines.append(f"  - [{channel}] {excerpt} {url}".strip())
            if url:
                candidates.append(
                    {
                        "url": str(url).strip(),
                        "project_name": "",
                        "channel": str(channel).lower(),
                        "match_text": f"{channel} {excerpt}",
                    }
                )

    return digest_md, "\n".join(lines), candidates


def _best_source_candidate(header: str, body: str, candidates: list[dict], used_urls: set[str]) -> str | None:
    insight_project = _extract_project_name_from_header(header)
    insight_tokens = _tokenize_match_text(f"{header} {body}")
    best_url: str | None = None
    best_score = 0

    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url or url in used_urls:
            continue
        candidate_tokens = _tokenize_match_text(str(candidate.get("match_text") or ""))
        overlap = len(insight_tokens & candidate_tokens)
        score = overlap
        if insight_project and insight_project == str(candidate.get("project_name") or "").strip():
            score += 4
        channel = str(candidate.get("channel") or "").strip()
        if channel and channel in (body or "").lower():
            score += 2
        if score > best_score:
            best_score = score
            best_url = url
    return best_url if best_score > 0 else None


def _rewrite_insight_source_urls(content: str, candidates: list[dict]) -> str:
    if not content or not candidates:
        return content

    parsed = parse_insights_html(content)
    if not parsed:
        return content

    rewritten = content
    used_urls: set[str] = set()
    for header, body, source_url, raw_html in parsed:
        replacement_url = _best_source_candidate(header, body, candidates, used_urls)
        if replacement_url is None:
            replacement_url = source_url.strip()
        if not replacement_url:
            continue
        updated_block = raw_html
        if source_url.strip():
            updated_block = updated_block.replace(source_url, replacement_url, 1)
        elif '<a href="' not in updated_block:
            updated_block = updated_block.rstrip() + f'\n<a href="{replacement_url}">источник</a>'
        updated_block = _keep_single_source_anchor(updated_block)
        rewritten = rewritten.replace(raw_html, updated_block, 1)
        used_urls.add(replacement_url)
    return rewritten


def _keep_single_source_anchor(block: str) -> str:
    lines: list[str] = []
    source_anchor_seen = False
    for line in block.splitlines():
        anchor_match = HTML_ANCHOR_RE.search(line)
        if not anchor_match:
            lines.append(line)
            continue
        label = _strip_html(anchor_match.group(2)).strip().lower()
        if "источник" not in label and "source" not in label:
            lines.append(line)
            continue
        if source_anchor_seen:
            continue
        source_anchor_seen = True
        lines.append(line)
    return "\n".join(lines)


def _load_completed_study_history(connection: sqlite3.Connection, limit: int = 6) -> str:
    rows = connection.execute(
        """
        SELECT week_label, topics_covered, COALESCE(completion_notes, '') AS completion_notes
        FROM study_plans
        WHERE completed_at IS NOT NULL
        ORDER BY completed_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    lines: list[str] = []
    for row in rows:
        topics = row["topics_covered"] or "[]"
        notes = str(row["completion_notes"] or "").strip()
        line = f"{row['week_label']}: topics={topics}"
        if notes:
            line += f"; notes={notes}"
        lines.append(line)
    return "\n".join(lines) if lines else "No completed study history yet."


def _write_insights_file(week_label: str, content: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights.md"
    output_path.write_text(_normalize_insights_delivery_text(content), encoding="utf-8")
    return output_path


def _section_heading_key(line: str) -> str:
    text = _strip_html(line).lower()
    for heading in INSIGHT_SECTION_HEADINGS:
        if heading in text:
            return heading
    return ""


def _is_triage_note_line(line: str) -> bool:
    text = _strip_html(line)
    if not text.startswith("("):
        return False
    return any(
        marker in text
        for marker in (
            "Сделать сейчас",
            "Бэклог",
            "Отложить",
            "Direct improvement",
            "New project concept",
            "Previously rejected",
        )
    )


def _normalize_insights_delivery_text(content: str) -> str:
    lines = (content or "").replace("\r\n", "\n").split("\n")
    normalized: list[str] = []
    for index, line in enumerate(lines):
        heading_key = _section_heading_key(line.strip())
        if heading_key:
            lookahead = index + 1
            while lookahead < len(lines):
                candidate = lines[lookahead].strip()
                if not candidate or _is_triage_note_line(candidate):
                    lookahead += 1
                    continue
                break
            if lookahead < len(lines) and _section_heading_key(lines[lookahead].strip()) == heading_key:
                continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def _html_to_copyable_text(content: str) -> str:
    def replace_anchor(match: re.Match) -> str:
        url = html.unescape(match.group(1).strip())
        label = _strip_html(match.group(2)).strip()
        if label and label != url:
            return f"{label}: {url}"
        return url

    content = _normalize_insights_delivery_text(content)
    text = HTML_ANCHOR_RE.sub(replace_anchor, content or "")
    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n" if text.strip() else ""


def _write_copyable_insights_file(week_label: str, content_html: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights_copy.txt"
    output_path.write_text(_html_to_copyable_text(content_html), encoding="utf-8")
    return output_path


def _send_copyable_insights_document(chat_id: str, week_label: str, content_html: str, token: str) -> None:
    try:
        copy_path = _write_copyable_insights_file(week_label, content_html)
        send_document(
            chat_id=chat_id,
            file_path=str(copy_path),
            caption=f"Copyable Implementation Ideas {week_label}",
            token=token,
        )
    except Exception:
        LOGGER.warning("Failed to send copyable implementation ideas week=%s", week_label, exc_info=True)


def _write_insights_html_file(week_label: str, content_html: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights.html"
    if "<html" in content_html.lower():
        html_content = content_html
    else:
        body_content = _render_insights_fragment(content_html)
        html_content = (
            "<html><head><meta charset=\"utf-8\"></head><body style=\"font-family: Georgia, serif; "
            "line-height: 1.68; color: #18212b; background: #f7f2e8; max-width: 860px; "
            "margin: 0 auto; padding: 20px;\">"
            "<style>"
            "body{font-size:17px;-webkit-user-select:text;user-select:text;}"
            "section.idea{background:#fffdf8;border:1px solid #eadfcb;border-radius:10px;padding:18px;margin:0 0 14px 0;}"
            "h2{font-size:22px;line-height:1.25;margin:0 0 12px 0;color:#102a43;}"
            "h3{font-size:18px;line-height:1.3;margin:18px 0 10px 0;color:#102a43;}"
            "h4{font-size:17px;line-height:1.35;margin:14px 0 8px 0;color:#102a43;}"
            "p{margin:0 0 12px 0;}"
            "a{color:#0b6bcb;text-decoration:none;}"
            "b{color:#0f1720;}"
            "</style>"
            f"<section class=\"idea\">{body_content}</section></body></html>"
        )
    output_path.write_text(html_content, encoding="utf-8")
    return output_path


def _render_insights_fragment(content: str) -> str:
    content = _normalize_insights_delivery_text(content)
    lines = [line.strip() for line in content.replace("\r\n", "\n").split("\n")]
    blocks: list[str] = []
    paragraph_parts: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_parts:
            blocks.append(" ".join(paragraph_parts).strip())
            paragraph_parts.clear()

    for line in lines:
        if not line:
            flush_paragraph()
            continue
        if line.startswith("<b>") and line.endswith("</b>"):
            flush_paragraph()
            blocks.append(line)
            continue
        if line.startswith("<a ") and line.endswith("</a>"):
            paragraph_parts.append(line)
            flush_paragraph()
            continue
        paragraph_parts.append(line)
    flush_paragraph()

    rendered_blocks: list[str] = []
    for index, block in enumerate(blocks):
        normalized = _normalize_inline_html(block)
        if not normalized:
            continue
        if normalized.startswith("<b>") and normalized.endswith("</b>"):
            stripped = _strip_html(normalized)
            if index == 0:
                tag = "h2"
            elif stripped.startswith(("[Implement]", "[Build]")):
                tag = "h4"
            elif "Собранные идеи" in stripped or "Отдельные сигналы" in stripped or "Built Ideas" in stripped or "Fresh Signals" in stripped:
                tag = "h3"
            else:
                tag = "p"
            rendered_blocks.append(f"<{tag}>{normalized}</{tag}>")
            continue
        if normalized.startswith("<a ") and normalized.endswith("</a>"):
            rendered_blocks.append(f"<p>{normalized}</p>")
            continue
        rendered_blocks.append(f"<p>{normalized}</p>")
    return "\n".join(rendered_blocks)


def _normalize_inline_html(text: str) -> str:
    normalized = text.strip()
    normalized = INLINE_URL_RE.sub(r'<a href="\1">\1</a>', normalized)
    return normalized


def _load_delivery_state(connection: sqlite3.Connection, week_label: str) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT COALESCE(telegraph_url, '') AS telegraph_url,
               COALESCE(telegram_sent_at, '') AS telegram_sent_at
        FROM recommendations
        WHERE week_label = ?
        LIMIT 1
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return {"telegraph_url": "", "telegram_sent_at": ""}
    return {
        "telegraph_url": str(row["telegraph_url"] or ""),
        "telegram_sent_at": str(row["telegram_sent_at"] or ""),
    }


def _mark_delivery_state(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    telegraph_url: str | None = None,
    telegram_sent_at: str | None = None,
) -> None:
    fields: list[str] = []
    params: list[str] = []
    if telegraph_url is not None:
        fields.append("telegraph_url = ?")
        params.append(telegraph_url)
    if telegram_sent_at is not None:
        fields.append("telegram_sent_at = ?")
        params.append(telegram_sent_at)
    if not fields:
        return
    params.append(week_label)
    connection.execute(
        f"UPDATE recommendations SET {', '.join(fields)} WHERE week_label = ?",
        params,
    )


def _store_recommendations(connection: sqlite3.Connection, week_label: str, content_md: str) -> None:
    connection.execute(
        """
        INSERT INTO recommendations (week_label, generated_at, content_md)
        VALUES (?, ?, ?)
        ON CONFLICT(week_label) DO UPDATE SET
            generated_at = excluded.generated_at,
            content_md = excluded.content_md
        """,
        (week_label, _utc_now_iso(), content_md),
    )


def _build_notification(week_label: str) -> str:
    return (
        f"Implementation Ideas {week_label} is ready.\n"
        "Open the full brief:"
    )[:300]


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", HTML_TAG_RE.sub(" ", html.unescape(value or ""))).strip()


def _load_feedback_cards(connection: sqlite3.Connection, week_label: str, limit: int = 3) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, title, reason, recommendation
        FROM insight_triage_records
        WHERE week_label = ?
          AND recommendation IN ('do_now', 'backlog')
        ORDER BY
            CASE recommendation
                WHEN 'do_now' THEN 0
                WHEN 'backlog' THEN 1
                ELSE 9
            END,
            id ASC
        LIMIT ?
        """,
        (week_label, limit),
    ).fetchall()


MAX_FEEDBACK_CARD_TEXT_CHARS = 420
MAX_FEEDBACK_CARD_REASON_CHARS = 180


def _truncate_card_text(value: str, limit: int) -> str:
    clean = _strip_html(value)
    if len(clean) <= limit:
        return clean
    trimmed = clean[: max(0, limit - 1)].rstrip()
    split_at = trimmed.rfind(" ")
    if split_at >= 60:
        trimmed = trimmed[:split_at].rstrip()
    return f"{trimmed}..."


def _build_feedback_card_text(row: sqlite3.Row, week_label: str) -> str:
    title = _strip_html(str(row["title"] or "Implementation idea"))
    reason = _strip_html(str(row["reason"] or ""))
    recommendation = str(row["recommendation"] or "")
    label = "Do now" if recommendation == "do_now" else "Backlog" if recommendation == "backlog" else "Idea"
    lines = [
        f"Implementation idea #{row['id']} | {week_label}",
        f"{label}: {_truncate_card_text(title, 140)}",
    ]
    if reason:
        lines.append(f"Why: {_truncate_card_text(reason, MAX_FEEDBACK_CARD_REASON_CHARS)}")
    lines.append("Choose:")
    return _truncate_card_text("\n".join(lines), MAX_FEEDBACK_CARD_TEXT_CHARS)


def _send_feedback_cards(connection: sqlite3.Connection, week_label: str, token: str, chat_id: str) -> None:
    for row in _load_feedback_cards(connection, week_label):
        send_text(
            chat_id=chat_id,
            text=_build_feedback_card_text(row, week_label),
            token=token,
            parse_mode=None,
            reply_markup=build_idea_feedback_markup(int(row["id"])),
        )


def _send_recommendations_to_telegram_owner(
    connection: sqlite3.Connection,
    week_label: str,
    content_md: str,
    html_path: Path | None,
    force_delivery: bool = False,
    operator_message: str | None = None,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    delivery_state = _load_delivery_state(connection, week_label)
    if delivery_state["telegram_sent_at"] and not force_delivery:
        LOGGER.info("Implementation ideas delivery skipped week=%s because it was already sent", week_label)
        return
    notification = operator_message or build_implementation_message(week_label=week_label, insights_html=content_md)
    write_weekly_message(week_label, "implementation", notification)
    if html_path is not None:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            url = publish_article(title=f"Implementation Ideas {week_label}", html_content=html_content)
            send_text(
                chat_id=chat_id,
                text=f"{notification}\n\nПолный audit-отчет: {url}"[:4096],
                token=token,
                parse_mode=None,
                reply_markup=build_artifact_feedback_markup(week_label, "implementation_ideas"),
            )
            _send_copyable_insights_document(chat_id, week_label, content_md, token)
            try:
                _send_feedback_cards(connection, week_label, token, chat_id)
            except Exception:
                LOGGER.warning("Failed to send implementation idea feedback cards week=%s", week_label, exc_info=True)
            _mark_delivery_state(connection, week_label, telegraph_url=url, telegram_sent_at=_utc_now_iso())
            connection.commit()
            LOGGER.info("Implementation ideas published to Telegraph week=%s url=%s", week_label, url)
            return
        except Exception:
            LOGGER.warning("Failed to publish implementation ideas week=%s", week_label, exc_info=True)
    send_text(
        chat_id=chat_id,
        text=notification[:4096],
        token=token,
        parse_mode=None,
        reply_markup=build_artifact_feedback_markup(week_label, "implementation_ideas"),
    )
    _send_copyable_insights_document(chat_id, week_label, content_md, token)
    try:
        _send_feedback_cards(connection, week_label, token, chat_id)
    except Exception:
        LOGGER.warning("Failed to send implementation idea feedback cards week=%s", week_label, exc_info=True)
    _mark_delivery_state(connection, week_label, telegram_sent_at=_utc_now_iso())
    connection.commit()


def run_recommendations(settings: Settings, force_delivery: bool = False) -> dict:
    week_label = _compute_week_label()
    db_path = settings.db_path

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        digest_md, digest_summary, digest_candidates = _load_digest_summary(connection, week_label)
        if digest_md is None:
            LOGGER.warning("Insights skipped because no digest exists for week=%s", week_label)
            return {"week_label": week_label, "output_path": None, "text": ""}

        sync_result = _maybe_sync_project_context(db_path)
        projects_context = _load_projects_context()
        try:
            project_context_snapshots = _load_project_context_snapshots(connection)
        except Exception:
            LOGGER.warning("Project context snapshot refresh failed; using empty context", exc_info=True)
            project_context_snapshots = "No project context snapshots available yet."
        freshness_report = _build_project_freshness_report(connection, sync_result=sync_result)
        if not freshness_report["gate_passed"]:
            delivery_text = build_project_freshness_blocked_message(
                week_label=week_label,
                freshness_report=freshness_report,
            )
            write_weekly_message(week_label, "implementation", delivery_text)
            output_path = _write_insights_file(week_label, delivery_text)
            html_path = _write_insights_html_file(week_label, delivery_text)
            _store_recommendations(connection, week_label, delivery_text)
            connection.commit()
            try:
                _send_recommendations_to_telegram_owner(
                    connection=connection,
                    week_label=week_label,
                    content_md=delivery_text,
                    html_path=html_path,
                    force_delivery=force_delivery,
                    operator_message=delivery_text,
                )
            except Exception:
                LOGGER.warning("Failed to send project freshness blocked message week=%s", week_label, exc_info=True)
            LOGGER.warning(
                "Insights generation blocked by stale project context week=%s reasons=%s",
                week_label,
                freshness_report["blocking_reasons"],
            )
            return {
                "week_label": week_label,
                "output_path": str(output_path),
                "text": delivery_text,
                "html_path": str(html_path),
                "project_freshness": freshness_report,
            }
        project_context_snapshots = f"{freshness_report['prompt_context']}\n\n{project_context_snapshots}"
        completed_study_history = _load_completed_study_history(connection)
        recent_decisions = _load_recent_decisions(connection)
        recent_evidence, evidence_candidates = _load_recent_project_evidence(connection)
        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{digest_summary}", digest_summary)
            .replace("{projects_context}", projects_context)
            .replace("{project_context_snapshots}", project_context_snapshots)
            .replace("{completed_study_history}", completed_study_history)
            .replace("{recent_decisions}", recent_decisions)
            .replace("{recent_evidence}", recent_evidence)
        )

        insights_text = complete(prompt=prompt, system=system_prompt, category="insight")
        insights_text = _rewrite_insight_source_urls(
            insights_text,
            evidence_candidates + digest_candidates,
        )

        # Triage: classify ideas and apply rejection memory before rendering
        triaged = triage_insights(insights_text, connection, week_label)
        connection.commit()

        delivery_text = _normalize_insights_delivery_text(render_triaged_insights_html(insights_text, triaged))
        implementation_message = build_implementation_message(
            week_label=week_label,
            insights_html=delivery_text,
        )
        write_weekly_message(week_label, "implementation", implementation_message)

        output_path = _write_insights_file(week_label, delivery_text)
        html_path = _write_insights_html_file(week_label, delivery_text)
        _store_recommendations(connection, week_label, delivery_text)
        connection.commit()
        try:
            _send_recommendations_to_telegram_owner(
                connection=connection,
                week_label=week_label,
                content_md=delivery_text,
                html_path=html_path,
                force_delivery=force_delivery,
            )
        except Exception:
            LOGGER.warning("Failed to send implementation ideas week=%s", week_label, exc_info=True)

    LOGGER.info(
        "Insights generation complete week=%s output=%s",
        week_label,
        output_path,
    )
    return {"week_label": week_label, "output_path": str(output_path), "text": delivery_text, "html_path": str(html_path)}


def generate_recommendations(settings: Settings) -> dict:
    return run_recommendations(settings)
