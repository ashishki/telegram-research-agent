from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable, Mapping

from config.settings import PROJECT_ROOT


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "weekly_messages"
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ANCHOR_RE = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
BOLD_RE = re.compile(r"<b>(.*?)</b>", re.IGNORECASE | re.DOTALL)
IMPLEMENT_HEADER_RE = re.compile(r"^\[(Implement|Build)\]\s+(.+?)\s+[—–-]\s+(.+)$", re.IGNORECASE)


def write_weekly_message(week_label: str, kind: str, text: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_kind = re.sub(r"[^a-z0-9_-]+", "-", kind.strip().lower()).strip("-") or "message"
    output_path = OUTPUT_DIR / f"{week_label}_{safe_kind}.md"
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    return output_path


def build_brief_message(
    *,
    week_label: str,
    posts: Iterable[Mapping[str, object]],
    bucket_counts: Mapping[str, int],
    top_topics: Iterable[Mapping[str, object]],
) -> str:
    post_list = [dict(post) for post in posts]
    signal_posts = [
        post
        for post in post_list
        if str(post.get("bucket") or "noise") in {"strong", "watch", "cultural"}
    ]
    ranked = sorted(
        signal_posts or post_list,
        key=lambda post: (
            -float(post.get("signal_score") or 0.0),
            -int(post.get("view_count") or 0),
        ),
    )
    stories = _pick_story_posts(ranked, limit=3)
    theme = _brief_theme(top_topics, stories)
    total = sum(int(value or 0) for value in bucket_counts.values()) or len(post_list)
    strong = int(bucket_counts.get("strong") or 0)
    watch = int(bucket_counts.get("watch") or 0)
    noise = int(bucket_counts.get("noise") or 0)

    lines = [
        f"Бриф недели {week_label}: {theme}",
        "",
        (
            f"Просмотрено {total} Telegram-постов. Полезных сигналов: "
            f"{strong} strong и {watch} watch; шум: {noise}."
        ),
        "",
    ]
    if not stories:
        lines.extend(
            [
                "Главный вывод: неделя не дала достаточно четких сигналов для новых действий.",
                "Что делать: не начинать новые сборки, а проверить ingestion/scoring и ждать более конкретных источников.",
            ]
        )
        return "\n".join(lines).strip()

    for index, post in enumerate(stories, start=1):
        title = _title_from_post(post)
        body = _summary_from_post(post)
        lines.append(f"{index}. {title}")
        if body:
            lines.append(body)
        why = _why_it_matters(post)
        if why:
            lines.append(f"Почему важно: {why}")
        source = _source_line(post)
        if source:
            lines.append(source)
        lines.append("")

    also = _also_line(ranked, exclude={int(post.get("id") or 0) for post in stories})
    if also:
        lines.append(f"Также: {also}")
    lines.append("Вывод: в работу брать только то, что превращается в конкретный PR или проверяемую MVP-гипотезу.")
    return _limit_message("\n".join(lines).strip(), 3200)


def build_implementation_message(*, week_label: str, insights_html: str) -> str:
    ideas = _parse_insight_ideas(insights_html)
    implement_ideas = [idea for idea in ideas if idea["kind"].lower() == "implement"][:3]
    lines = [f"Implementation {week_label}", ""]
    if not implement_ideas:
        lines.extend(
            [
                "На этой неделе нет достаточно конкретных улучшений для текущих репозиториев.",
                "Правило: сюда попадают только изменения существующих проектов, не новые MVP.",
            ]
        )
        return "\n".join(lines).strip()

    for index, idea in enumerate(implement_ideas, start=1):
        lines.append(f"{index}. {idea['project']} — {idea['title']}")
        if idea["body"]:
            lines.append(f"Что сделать: {_truncate(idea['body'], 360)}")
        lines.append("Критерий готовности: один узкий PR или один backlog item с проверяемым результатом.")
        if idea["source"]:
            lines.append(f"Источник: {idea['source']}")
        lines.append("")

    lines.append("Важно: это не новые продукты. Это улучшения уже открытых репозиториев.")
    return _limit_message("\n".join(lines).strip(), 3200)


def build_mvp_message(
    *,
    week_label: str,
    title: str | None,
    status: str | None,
    recommendation: str | None,
    score: int | None,
    source_mix: Mapping[str, object] | None = None,
    live_intelligence: Mapping[str, object] | None = None,
) -> str:
    normalized_recommendation = str(recommendation or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    title_text = title or "кандидат не выбран"
    score_text = f", score {score}/100" if score is not None else ""
    source_mix = source_mix or {}
    live_intelligence = live_intelligence or {}
    selected_external = _safe_int(source_mix.get("selected_external_evidence_count"))
    selected_telegram = _safe_int(source_mix.get("selected_telegram_seed_evidence_count"))
    repeated_live = _safe_int(live_intelligence.get("repeated_claim_count"))

    lines = [f"MVP {week_label}: {title_text}", ""]
    if normalized_recommendation == "existing_project_context":
        lines.append("Решение: это не standalone MVP, а контекст для существующего проекта.")
    elif normalized_recommendation in {
        "revisit_with_evidence_gap",
        "needs_more_evidence",
        "needs_more_specific_scope",
        "reject",
    } or normalized_status in {"investigate", "reject"}:
        lines.append("Решение: MVP не выбран как build-ready.")
    else:
        lines.append(f"Решение: можно рассматривать узкий эксперимент{score_text}.")

    lines.append(
        (
            "Почему: выбранный кандидат имеет "
            f"{selected_telegram} Telegram seed evidence и {selected_external} decision-grade external evidence."
        )
    )
    if repeated_live:
        lines.append(f"Live intelligence: {repeated_live} повторяющихся claim-кандидатов.")
    else:
        lines.append("Live intelligence: повторяющихся claim-кандидатов пока нет; Pathway-sidecar рано.")

    if normalized_recommendation in {
        "revisit_with_evidence_gap",
        "needs_more_evidence",
        "needs_more_specific_scope",
        "reject",
    } or selected_external < 2:
        lines.extend(
            [
                "",
                "Что проверить до сборки:",
                "1. Найти 2 независимых внешних источника той же боли.",
                "2. Найти повторяемый search/query/workaround pattern.",
                "3. Получить хотя бы один сигнал willingness-to-pay или срочности.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Следующий шаг: собрать one-function MVP за 7 дней и зафиксировать build/revisit/reject.",
            ]
        )
    return _limit_message("\n".join(lines).strip(), 2800)


def _pick_story_posts(posts: list[dict], *, limit: int) -> list[dict]:
    stories: list[dict] = []
    seen_topics: set[str] = set()
    for post in posts:
        topic = str(post.get("topic_label") or "").strip().lower()
        if topic and topic in seen_topics and len(stories) < limit - 1:
            continue
        stories.append(post)
        if topic:
            seen_topics.add(topic)
        if len(stories) >= limit:
            break
    return stories


def _brief_theme(top_topics: Iterable[Mapping[str, object]], stories: list[dict]) -> str:
    for topic in top_topics:
        label = str(topic.get("label") or "").strip()
        if label and label.lower() != "unlabeled":
            return _clean_title(label, 80)
    for post in stories:
        title = _title_from_post(post)
        if title:
            return _clean_title(title, 80)
    return "сигналы недели без одного доминирующего сюжета"


def _title_from_post(post: Mapping[str, object]) -> str:
    content = _clean_text(str(post.get("content") or ""))
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if not first_line:
        first_line = content
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0]
    return _clean_title(first_sentence, 96)


def _summary_from_post(post: Mapping[str, object]) -> str:
    content = _clean_text(str(post.get("content") or ""))
    title = _title_from_post(post)
    body = content
    if body.startswith(title):
        body = body[len(title) :].strip(" -—–:\n")
    sentences = re.split(r"(?<=[.!?])\s+", body)
    summary = " ".join(sentence.strip() for sentence in sentences if sentence.strip())[:420]
    return _truncate(summary, 360)


def _why_it_matters(post: Mapping[str, object]) -> str:
    topic = str(post.get("topic_label") or "").strip()
    bucket = str(post.get("bucket") or "").strip()
    if topic and topic.lower() != "unlabeled":
        return f"это усиливает тему `{topic}` и попало в bucket `{bucket or 'watch'}`."
    return f"сигнал попал в bucket `{bucket or 'watch'}` и заслуживает проверки, а не немедленной сборки."


def _source_line(post: Mapping[str, object]) -> str:
    channel = str(post.get("channel_username") or "").strip()
    url = str(post.get("message_url") or "").strip()
    if channel and url:
        return f"Источник: {channel} | {url}"
    if url:
        return f"Источник: {url}"
    return ""


def _also_line(posts: list[dict], *, exclude: set[int]) -> str:
    titles: list[str] = []
    for post in posts:
        post_id = int(post.get("id") or 0)
        if post_id in exclude:
            continue
        title = _title_from_post(post)
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= 3:
            break
    return "; ".join(titles)


def _parse_insight_ideas(content: str) -> list[dict[str, str]]:
    normalized = _normalize_html_text(content)
    lines = [line.strip() for line in normalized.splitlines()]
    ideas: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal current, body_lines
        if current is None:
            return
        current["body"] = _clean_text(" ".join(body_lines))
        ideas.append(current)
        current = None
        body_lines = []

    for line in lines:
        if not line:
            continue
        match = IMPLEMENT_HEADER_RE.match(line)
        if match:
            flush()
            current = {
                "kind": match.group(1),
                "project": match.group(2).strip(),
                "title": match.group(3).strip(),
                "body": "",
                "source": "",
            }
            continue
        if current is None:
            continue
        if line.lower().startswith("источник:") or line.startswith("http"):
            current["source"] = re.sub(r"^источник:\s*", "", line, count=1, flags=re.IGNORECASE).strip()
            continue
        if line.startswith("(") and line.endswith(")"):
            continue
        body_lines.append(line)
    flush()
    return ideas


def _normalize_html_text(content: str) -> str:
    def anchor(match: re.Match) -> str:
        url = html.unescape(match.group(1).strip())
        label = _strip_html(match.group(2)).strip()
        if label.lower() in {"источник", "source"}:
            return f"Источник: {url}"
        return f"{label}: {url}" if label and label != url else url

    text = HTML_ANCHOR_RE.sub(anchor, content or "")
    text = BOLD_RE.sub(lambda match: "\n" + _strip_html(match.group(1)).strip() + "\n", text)
    text = _strip_html(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_html(value: str) -> str:
    text = HTML_TAG_RE.sub("\n", html.unescape(value or ""))
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines()).strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _clean_title(value: str, limit: int) -> str:
    value = _clean_text(value).strip(" -*•")
    return _truncate(value, limit) or "сигнал недели"


def _truncate(value: str, limit: int) -> str:
    value = _clean_text(value)
    if len(value) <= limit:
        return value
    trimmed = value[: max(0, limit - 1)].rstrip()
    split_at = trimmed.rfind(" ")
    if split_at >= max(24, limit // 2):
        trimmed = trimmed[:split_at].rstrip()
    return f"{trimmed}…"


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _limit_message(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return _truncate(text, limit)
