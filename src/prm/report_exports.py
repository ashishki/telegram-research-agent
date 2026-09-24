"""Private, source-preserving projections of immutable ``BriefDocument`` values.

This module deliberately has no web server, delivery adapter, filesystem output,
or provider call.  It renders an already-authorized immutable document in memory.
``PrivateBriefReportReader`` adds a short-lived, owner-bound local access handle
for a future transport boundary; it does not turn a report into a public link.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import hmac
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Literal, Sequence
from urllib.parse import urlsplit
import zlib

from prm.briefs import (
    BriefDocument,
    BriefDocumentStore,
    BriefEvidence,
    brief_owner_ref_from_authenticated_private_tuple,
)


REPORT_RENDERER_VERSION = "prm_brief_report.v1"
REPORT_ACCESS_TTL = timedelta(minutes=20)
_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; "
    "script-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-src 'none'"
)
_FORBIDDEN_HTML_TAGS = frozenset({
    "script", "iframe", "object", "embed", "form", "input", "button", "link", "base",
    "img", "video", "audio", "source", "track",
})


class BriefReportRenderError(ValueError):
    """The document cannot safely be projected into a requested local format."""


class BriefReportRenderUnavailable(BriefReportRenderError):
    """A local rendering dependency is unavailable; no alternate egress is used."""


@dataclass(frozen=True, slots=True)
class BriefReportIdentity:
    """The immutable identity shared by every format of one report version."""

    brief_id: str
    version: int
    content_digest: str
    source_refs: tuple[str, ...]
    renderer_version: str = REPORT_RENDERER_VERSION


@dataclass(frozen=True, slots=True)
class BriefReportArtifact:
    """An in-memory local representation, never a delivery receipt or public URL."""

    format: Literal["html", "markdown", "pdf"]
    media_type: str
    body: str | bytes
    identity: BriefReportIdentity


@dataclass(frozen=True, slots=True)
class BriefReportAccess:
    """An opaque, short-lived reference to one exact private report version."""

    access_ref: str
    brief_id: str
    version: int
    content_digest: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class BriefSharePreview:
    """Exact content and recipient preview; it intentionally has no send operation."""

    recipient_label: str
    artifact: BriefReportArtifact
    expires_at: datetime
    delivery_state: Literal["preview_only_no_delivery"] = "preview_only_no_delivery"


def report_identity(document: BriefDocument) -> BriefReportIdentity:
    """Expose the document/version and source set every renderer must preserve."""

    _require_document(document)
    return BriefReportIdentity(
        brief_id=document.brief_id,
        version=document.version,
        content_digest=document.content_digest,
        source_refs=tuple(item.source_ref for item in document.evidence),
    )


def render_markdown(document: BriefDocument) -> BriefReportArtifact:
    """Render a portable, source-complete Markdown projection without HTML."""

    _require_document(document)
    identity = report_identity(document)
    lines = [
        f"# {_markdown_text(document.topic)}",
        "",
        f"- Версия: `{document.brief_id}` v{document.version}",
        f"- Идентичность содержимого: `{document.content_digest}`",
        f"- Период: {_markdown_text(_period_text(document))}",
        f"- Статус покрытия: {_markdown_text(document.status)}",
        "",
        "## Главное",
        "",
    ]
    lines.extend(_markdown_story_or_item_lines(document))
    lines.extend(("", "## Временная линия источников", ""))
    for evidence in _timeline(document):
        lines.extend((
            f"- **{_markdown_text(_display_time(evidence))}** — {_markdown_text(evidence.title)}",
            f"  - {_markdown_text(evidence.summary)}",
            f"  - Источник: {_markdown_source(evidence.source_ref)}",
        ))
    lines.extend(("", "## Покрытие", "", "| Источник | Состояние | Ограничение |", "| --- | --- | --- |"))
    for item in document.coverage_manifest.sources:
        lines.append(
            "| " + " | ".join(
                _markdown_table(value) for value in (item.source_ref, item.state, item.reason or "—")
            ) + " |"
        )
    if document.coverage_manifest.limitations:
        lines.extend(("", "Ограничения: " + ", ".join(_markdown_text(item) for item in document.coverage_manifest.limitations)))
    lines.extend(("", "## Источники", ""))
    for evidence in document.evidence:
        lines.extend((
            f"### {_markdown_text(evidence.title)}",
            "",
            _markdown_text(evidence.summary),
            "",
            f"- URL: {_markdown_source(evidence.source_ref)}",
            f"- Время: {_markdown_text(_display_time(evidence))}",
            f"- Состояние: {_markdown_text(evidence.source_state)}; отношение к периоду: {_markdown_text(evidence.period_relation)}",
            "",
        ))
    return BriefReportArtifact("markdown", "text/markdown; charset=utf-8", "\n".join(lines).rstrip() + "\n", identity)


def render_html(document: BriefDocument) -> BriefReportArtifact:
    """Render static, responsive report HTML with no executable or tracked resources."""

    _require_document(document)
    identity = report_identity(document)
    topic = _html_text(document.topic)
    story_or_items = _html_story_or_item_sections(document)
    timeline_rows = "".join(
        "<li><time datetime=\"{time}\">{time}</time><div><strong>{title}</strong><p>{summary}</p>{source}</div></li>".format(
            time=_html_attr(_iso(evidence.observed_at)),
            title=_html_text(evidence.title),
            summary=_html_text(evidence.summary),
            source=_html_source(evidence.source_ref),
        )
        for evidence in _timeline(document)
    )
    coverage_rows = "".join(
        "<tr><td>{source}</td><td>{state}</td><td>{reason}</td></tr>".format(
            source=_html_source_label(item.source_ref),
            state=_html_text(item.state),
            reason=_html_text(item.reason or "—"),
        )
        for item in document.coverage_manifest.sources
    )
    limitation = "".join(f"<li>{_html_text(item)}</li>" for item in document.coverage_manifest.limitations)
    source_rows = "".join(
        "<article class=\"source-card\"><h3>{title}</h3><p>{summary}</p><p>{source}</p>"
        "<dl><dt>Время</dt><dd>{time}</dd><dt>Состояние</dt><dd>{state}</dd>"
        "<dt>Отношение к периоду</dt><dd>{relation}</dd></dl></article>".format(
            title=_html_text(evidence.title),
            summary=_html_text(evidence.summary),
            source=_html_source(evidence.source_ref),
            time=_html_text(_display_time(evidence)),
            state=_html_text(evidence.source_state),
            relation=_html_text(evidence.period_relation),
        )
        for evidence in document.evidence
    )
    sources_section = (
        f'  <section aria-labelledby="sources-heading"><p class="eyebrow">Проверяемые основания</p>'
        f'<h2 id="sources-heading">Источники</h2><div class="source-grid">{source_rows}</div></section>'
        if source_rows
        else
        '  <section aria-labelledby="sources-heading"><p class="eyebrow">Проверяемые основания</p>'
        '<h2 id="sources-heading">Источники</h2>'
        '<p class="caveat">В выбранном окне нет источников для показа.</p></section>'
    )
    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<title>{topic}</title>
<style>{_stylesheet()}</style>
</head>
<body>
<main class="brief-report" data-surface="private_brief_report" data-brief-id="{_html_attr(document.brief_id)}" data-version="{document.version}" data-content-digest="{_html_attr(document.content_digest)}">
  <header class="hero">
    <p class="eyebrow">Private BriefDocument</p>
    <h1>{topic}</h1>
    <p class="period">{_html_text(_period_text(document))}</p>
    <dl class="identity"><dt>Версия</dt><dd>{_html_text(document.brief_id)} v{document.version}</dd><dt>Идентичность содержимого</dt><dd><code>{_html_text(document.content_digest)}</code></dd><dt>Покрытие</dt><dd>{_html_text(document.status)}</dd></dl>
  </header>
  <section aria-labelledby="main-heading"><p class="eyebrow">Главное</p><h2 id="main-heading">События и объяснения</h2>{story_or_items}</section>
  <section aria-labelledby="timeline-heading"><p class="eyebrow">Контекст времени</p><h2 id="timeline-heading">Временная линия источников</h2><ol class="timeline">{timeline_rows}</ol></section>
  <section aria-labelledby="coverage-heading"><p class="eyebrow">Границы выборки</p><h2 id="coverage-heading">Покрытие</h2><div class="table-wrap"><table><thead><tr><th>Источник</th><th>Состояние</th><th>Ограничение</th></tr></thead><tbody>{coverage_rows}</tbody></table></div>{_html_limitations(limitation)}</section>
{sources_section}
</main>
</body>
</html>"""
    validate_report_html(html)
    return BriefReportArtifact("html", "text/html; charset=utf-8", html, identity)


def render_pdf(document: BriefDocument) -> BriefReportArtifact:
    """Render the static HTML locally into a PDF; resource fetches fail closed.

    The regular renderer is WeasyPrint.  Some development environments have a
    broken WeasyPrint/pydyf pair despite the declared dependency being present;
    the bounded local fallback embeds DejaVu Sans and renders the same document
    text without fetching a URL.  It exists only to keep private export usable
    under that local dependency fault.
    """

    html_artifact = render_html(document)
    try:
        body = _render_with_weasyprint(str(html_artifact.body))
    except Exception:
        body = _render_fallback_pdf(document)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise BriefReportRenderUnavailable("local PDF renderer returned an invalid artifact")
    return BriefReportArtifact("pdf", "application/pdf", body, html_artifact.identity)


def render_designed_html(document: BriefDocument) -> BriefReportArtifact:
    """A richer analytical layout: cover, KPI blocks, chart, then the same facts."""

    _require_document(document)
    identity = report_identity(document)
    topic = _html_text(document.topic)
    story_or_items = _html_story_or_item_sections(document)
    chart = _designed_chart_svg(document)
    sources = document.evidence_by_ref()
    source_cards = "".join(
        "<article class=\"source-card\"><h3>{title}</h3><p>{summary}</p><p>{source}</p>"
        "<p class=\"source-meta\">{time} · {state}</p></article>".format(
            title=_html_text(evidence.title),
            summary=_html_text(evidence.summary),
            source=_html_source(evidence.source_ref),
            time=_html_text(_display_time(evidence)),
            state=_html_text(evidence.source_state),
        )
        for evidence in document.evidence
    )
    limitation = "".join(f"<li>{_html_text(item)}</li>" for item in document.coverage_manifest.limitations)
    coverage_rows = "".join(
        "<tr><td>{source}</td><td>{state}</td><td>{reason}</td></tr>".format(
            source=_html_source_label(item.source_ref),
            state=_html_text(item.state),
            reason=_html_text(item.reason or "—"),
        )
        for item in document.coverage_manifest.sources
    )
    kpis = (
        ("items", len(document.items), "пунктов"),
        ("sources", len(document.evidence), "источников"),
        ("conflicts", len(document.conflicts), "конфликтов дат"),
        ("coverage", "полное" if document.coverage_manifest.complete else "частичное", "покрытие"),
    )
    kpi_html = "".join(
        f'<div class="kpi"><span class="kpi-value">{_html_text(value)}</span>'
        f'<span class="kpi-label">{_html_text(label)}</span></div>'
        for _, value, label in kpis
    )
    top_sources = _designed_top_sources_svg(document)
    chart_section = (
        f'  <section class="keep" aria-labelledby="chart-heading"><p class="eyebrow">Динамика</p>'
        f'<h2 id="chart-heading">Наблюдения по дням</h2>{chart}</section>'
        if chart
        else ""
    )
    sources_chart_section = (
        f'  <section class="keep" aria-labelledby="topsources-heading"><p class="eyebrow">Источники</p>'
        f'<h2 id="topsources-heading">Пункты по источникам</h2>{top_sources}</section>'
        if top_sources
        else ""
    )
    cover_lead = ""
    if document.editorial is not None and document.editorial.stories:
        cover_lead = f'<p class="cover-lead">{_html_text(document.editorial.stories[0].summary)}</p>'
    # The cover carries the editorial label; stories then start immediately, so
    # no section heading can be orphaned at a page bottom.
    cover_eyebrow = (
        "Аналитический бриф"
        if document.editorial is not None
        else "Выдержки из источников (без редакторской переработки)"
    )
    story_or_items = f'<div class="story-stack">{story_or_items}</div>'
    sources_section = (
        f'  <section aria-labelledby="sources-heading"><p class="eyebrow">Проверяемые основания</p>'
        f'<h2 id="sources-heading">Источники</h2><div class="source-grid">{source_cards}</div></section>'
        if source_cards
        else
        '  <section aria-labelledby="sources-heading"><p class="eyebrow">Проверяемые основания</p>'
        '<h2 id="sources-heading">Источники</h2>'
        '<p class="caveat">В выбранном окне нет источников для показа.</p></section>'
    )
    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<title>{topic}</title>
<style>{_stylesheet()}{_designed_stylesheet()}</style>
</head>
<body>
<main class="brief-report brief-report--designed" data-surface="private_brief_report" data-brief-id="{_html_attr(document.brief_id)}" data-version="{document.version}" data-content-digest="{_html_attr(document.content_digest)}">
  <header class="cover">
    <p class="eyebrow">{cover_eyebrow}</p>
    <h1>{topic}</h1>
    <p class="period">{_html_text(_period_text(document))}</p>
{cover_lead}
    <div class="kpis">{kpi_html}</div>
  </header>
  <section class="main" aria-label="Главное">{story_or_items}</section>
{chart_section}
{sources_chart_section}
  <section aria-labelledby="coverage-heading"><p class="eyebrow">Границы выборки</p><h2 id="coverage-heading">Покрытие</h2><div class="table-wrap"><table><thead><tr><th>Источник</th><th>Состояние</th><th>Ограничение</th></tr></thead><tbody>{coverage_rows}</tbody></table></div>{_html_limitations(limitation)}</section>
{sources_section}
</main>
</body>
</html>"""
    validate_report_html(html)
    return BriefReportArtifact("html", "text/html; charset=utf-8", html, identity)


def render_designed_pdf(document: BriefDocument) -> BriefReportArtifact:
    """Render the designed HTML to PDF locally; fall back to the plain PDF."""

    html_artifact = render_designed_html(document)
    try:
        body = _render_with_weasyprint(str(html_artifact.body))
    except Exception:
        body = _render_fallback_pdf(document)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise BriefReportRenderUnavailable("local PDF renderer returned an invalid artifact")
    return BriefReportArtifact("pdf", "application/pdf", body, html_artifact.identity)


def _chunk(items: Sequence[Any], size: int) -> list[list[Any]]:
    size = max(1, size)
    return [list(items[index:index + size]) for index in range(0, len(items), size)]


def _estimate_card_mm(html: str) -> float:
    """Rough card height in mm from its visible text, deliberately generous."""

    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    # Deliberately conservative so an underestimate cannot silently clip text.
    lines = max(3, len(text) / 55.0)
    return 18.0 + lines * 5.6


def _pack_cards(cards: Sequence[str], *, page_mm: float = 232.0) -> list[list[str]]:
    """Greedy single-column packing so fixed pages are never nearly empty."""

    pages: list[list[str]] = []
    current: list[str] = []
    used = 0.0
    for card in cards:
        height = _estimate_card_mm(card)
        if height > page_mm:
            # Refuse to silently clip: a single card that cannot fit a fixed page
            # is an explicit render error, not hidden overflow.
            raise BriefReportRenderError("page_overflow: a single card exceeds one page")
        if current and used + height > page_mm:
            pages.append(current)
            current = []
            used = 0.0
        current.append(card)
        used += height
    if current:
        pages.append(current)
    return pages


def render_paginated_html(
    document: BriefDocument,
    *,
    stories_per_page: int | None = None,
    sources_per_page: int | None = None,
) -> BriefReportArtifact:
    """Fixed A4 page composition: no engine pagination, no orphan headings."""

    _require_document(document)
    # stories_per_page None means adaptive packing by estimated card height.
    if sources_per_page is None:
        sources_per_page = 8  # compact reader rows are short
    identity = report_identity(document)
    topic = _html_text(document.topic)
    period = _html_text(_period_text(document))
    cover_eyebrow = (
        "Аналитический бриф"
        if document.editorial is not None
        else "Выдержки из источников (без редакторской переработки)"
    )
    lead = ""
    if document.editorial is not None and document.editorial.stories:
        lead = f'<p class="cover-lead">{_html_text(document.editorial.stories[0].summary)}</p>'
    stories = document.editorial.stories if document.editorial is not None else ()
    shown = len(stories) if stories else len(document.items)
    try:
        days = max(1, (document.window.end_at - document.window.start_at).days)
    except Exception:
        days = 7
    kpis = (
        ("sources", len(document.evidence), "материалов"),
        ("stories", shown, "тем"),
        ("days", days, "дней"),
    )
    kpi_html = "".join(
        f'<div class="kpi"><span class="kpi-value">{_html_text(value)}</span>'
        f'<span class="kpi-label">{_html_text(label)}</span></div>'
        for _, value, label in kpis
    )
    coverage_note = (
        "Все выбранные материалы показаны."
        if document.coverage_manifest.complete
        else "Показаны не все материалы периода: это ограниченная выборка поиска по архиву."
    )
    select_note = (
        f'<p class="select-note">Поиск по «{topic}» за {period}. Из {len(document.evidence)} '
        f"найденных материалов отобрано {shown} тем по релевантности поиска и редакционной "
        f"оценке. {coverage_note}</p>"
    )
    reader_sources = _reader_source_card_blocks(document)
    pages: list[str] = []

    def add_page(section_title: str, body: str) -> None:
        pages.append(
            '<section class="page">'
            f'<header class="page-head"><span>{topic}</span>'
            f'<span>{_html_text(section_title)}</span></header>'
            f'<div class="page-body">{body}</div>'
            f'<footer class="page-foot">Страница {len(pages) + 1} / __TOTAL__</footer>'
            "</section>"
        )

    if document.editorial is not None and document.editorial.stories:
        titles = [story.title for story in document.editorial.stories]
    else:
        titles = [item.title for section in document.sections for item in section.items]
    contents = "".join(f"<li>{_html_text(title)}</li>" for title in titles[:10])
    toc = f'<ol class="toc">{contents}</ol>' if contents else ""
    add_page(
        "Обзор",
        f'<div class="cover"><p class="eyebrow">{cover_eyebrow}</p><h1>{topic}</h1>'
        f'<p class="period">{period}</p>{lead}<div class="kpis">{kpi_html}</div>'
        f"{select_note}{toc}</div>",
    )
    story_cards = _story_card_blocks(document)
    if stories_per_page is None:
        story_pages = _pack_cards(story_cards)
    else:
        story_pages = _chunk(story_cards, stories_per_page)
    for chunk in story_pages:
        add_page("Главное", f'<div class="story-stack">{"".join(chunk)}</div>')
    for chunk in _chunk(reader_sources, sources_per_page):
        add_page("Источники", f'<div class="source-list">{"".join(chunk)}</div>')
    total = len(pages)
    body = "".join(pages).replace("__TOTAL__", str(total))
    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<title>{topic}</title>
<style>{_stylesheet()}{_designed_stylesheet()}{_paginated_stylesheet()}</style>
</head>
<body>
<main class="brief-doc" data-surface="private_brief_report" data-brief-id="{_html_attr(document.brief_id)}" data-version="{document.version}" data-content-digest="{_html_attr(document.content_digest)}">
{body}
</main>
</body>
</html>"""
    validate_report_html(html)
    return BriefReportArtifact("html", "text/html; charset=utf-8", html, identity)


def render_paginated_pdf(document: BriefDocument) -> BriefReportArtifact:
    """Render the fixed-page HTML to PDF locally; fall back to the plain PDF."""

    html_artifact = render_paginated_html(document)
    try:
        body = _render_with_weasyprint(str(html_artifact.body))
    except Exception:
        body = _render_fallback_pdf(document)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise BriefReportRenderUnavailable("local PDF renderer returned an invalid artifact")
    return BriefReportArtifact("pdf", "application/pdf", body, html_artifact.identity)


def _paginated_stylesheet() -> str:
    return """
.brief-doc { background: var(--bg); }
.page { position: relative; width: 210mm; height: 297mm; box-sizing: border-box; padding: 13mm 14mm 16mm; background: var(--bg); break-after: page; break-inside: avoid; overflow: hidden; }
.page:last-of-type { break-after: auto; }
.page-head { display: flex; justify-content: space-between; gap: 8px; font-size: 8pt; color: var(--muted); border-bottom: 1px solid var(--line); padding-bottom: 3mm; margin-bottom: 6mm; }
.page-body { height: 236mm; overflow: hidden; }
.page-foot { position: absolute; left: 14mm; right: 14mm; bottom: 6mm; text-align: center; font-size: 8pt; color: var(--muted); }
.page .cover { padding: 0; border: 0; }
.page .cover h1 { font-size: 2.4rem; max-width: 22ch; }
.page .toc { margin: 16px 0 0; padding-left: 22px; }
.page .toc li { margin: 5px 0; font-size: .95rem; }
.page .cover-chart { margin-top: 16px; }
.page .cover-chart h3 { margin: 0 0 4px; font-size: 1rem; }
.select-note { margin: 14px 0 0; font-size: .9rem; color: var(--muted); line-height: 1.45; }
.source-list { display: block; }
.source-row { display: block; padding: 11px 2px; border-bottom: 1px solid var(--line); line-height: 1.4; }
.source-row .source-num { display: inline-block; min-width: 22px; color: var(--accent); font-weight: 700; }
.source-row .source-title { display: block; margin: 0 0 3px 22px; font-size: .98rem; font-weight: 650; color: var(--ink); }
.source-row .source-link { display: block; margin-left: 22px; font-size: .86rem; }
.page .story-stack .story:first-child { margin-top: 0; }
@media print { .page { break-after: page; } .page:last-of-type { break-after: auto; } }
"""


def _designed_chart_svg(document: BriefDocument) -> str:
    """Deterministic inline-SVG bar chart of observations per day (no egress)."""

    from collections import Counter

    counts: Counter[str] = Counter()
    for evidence in document.evidence:
        try:
            counts[evidence.observed_at.date().isoformat()] += 1
        except Exception:
            continue
    if not counts:
        return ""
    days = sorted(counts)
    maximum = max(counts.values())
    width, height, pad = 720, 220, 30
    left = pad + 34
    baseline = height - pad - 22
    usable = height - pad - pad - 22
    slot = (width - left - pad) / max(1, len(days))
    bar_width = slot * 0.68
    parts: list[str] = []
    # Light y-axis with gridlines and value labels so the chart is readable.
    parts.append(f'<line class="chart-axis" x1="{left - 6}" y1="{baseline}" x2="{width - pad}" y2="{baseline}"/>')
    parts.append(f'<line class="chart-axis" x1="{left - 6}" y1="{pad}" x2="{left - 6}" y2="{baseline}"/>')
    for step in (0, maximum / 2, maximum):
        y = baseline - usable * (step / maximum) if maximum else baseline
        parts.append(f'<line class="chart-grid" x1="{left - 6}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}"/>')
        parts.append(
            f'<text class="chart-ylabel" x="{left - 10}" y="{y + 3:.1f}" text-anchor="end">'
            f'{int(step) if float(step).is_integer() else round(step, 1)}</text>'
        )
    for index, day in enumerate(days):
        value = counts[day]
        bar_height = usable * (value / maximum)
        x = left + index * slot + (slot - bar_width) / 2
        y = baseline - bar_height
        centre = x + bar_width / 2
        parts.append(
            f'<rect class="chart-bar" x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" rx="4"/>'
        )
        parts.append(
            f'<text class="chart-label" x="{centre:.1f}" y="{height - pad + 2:.1f}" '
            f'text-anchor="middle">{_html_text(day[5:])}</text>'
        )
        parts.append(
            f'<text class="chart-value" x="{centre:.1f}" y="{y - 5:.1f}" '
            f'text-anchor="middle">{value}</text>'
        )
    return (
        f'<svg class="chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Наблюдения по дням">{"".join(parts)}</svg>'
    )


def _designed_top_sources_svg(document: BriefDocument) -> str:
    """Deterministic horizontal bars: selected items per source host."""

    from collections import Counter
    from urllib.parse import urlparse

    counts: Counter[str] = Counter()
    for evidence in document.evidence:
        host = urlparse(str(evidence.source_ref)).hostname or ""
        host = host[4:] if host.startswith("www.") else host
        if host:
            counts[host] += 1
    if not counts:
        return ""
    items = counts.most_common(6)
    maximum = max(counts.values())
    width, row_height, pad, label_width = 720, 30, 12, 220
    height = pad * 2 + len(items) * row_height
    parts: list[str] = []
    for index, (host, value) in enumerate(items):
        y = pad + index * row_height
        bar_width = (width - label_width - 70) * (value / maximum)
        parts.append(
            f'<text class="hbar-label" x="{label_width - 12}" y="{y + 15}" text-anchor="end">{_html_text(host)}</text>'
        )
        parts.append(
            f'<rect class="hbar-bar" x="{label_width}" y="{y + 3}" width="{bar_width:.1f}" height="16" rx="4"/>'
        )
        parts.append(
            f'<text class="hbar-value" x="{label_width + bar_width + 8:.1f}" y="{y + 16}">{value}</text>'
        )
    return (
        f'<svg class="hbar" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Пункты по источникам">{"".join(parts)}</svg>'
    )


def _designed_stylesheet() -> str:
    return """
.brief-report--designed .cover { padding: 28px 0 22px; border-bottom: 2px solid var(--accent); }
.keep { break-inside: avoid; }
.brief-report--designed .cover h1 { font-size: clamp(2.2rem, 8vw, 3.8rem); max-width: 24ch; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin: 22px 0 0; }
.kpi { flex: 1 1 150px; min-width: 140px; display: block; padding: 14px 16px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); }
.kpi-value { display: block; font-size: 1.35rem; font-weight: 800; line-height: 1.15; overflow-wrap: break-word; }
.kpi-label { display: block; margin-top: 4px; font-size: .8rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; overflow-wrap: normal; }
.chart { width: 100%; height: 210px; margin-top: 8px; }
.chart-bar { fill: var(--accent); }
.chart-label { fill: #586161; font-size: 12px; }
.chart-value { fill: #1e2525; font-size: 12px; font-weight: 700; }
.chart-axis { stroke: #9aa4a0; stroke-width: 1; }
.chart-grid { stroke: #e3e8e4; stroke-width: 1; }
.chart-ylabel { fill: #4f5858; font-size: 10px; }
.hbar { width: 100%; height: auto; margin-top: 8px; }
.hbar-bar { fill: #146b5c; }
.hbar-label { fill: #4f5858; font-size: 12px; }
.hbar-value { fill: #1e2525; font-size: 12px; font-weight: 700; }
.cover-lead { margin: 18px 0 0; padding: 14px 16px; border-left: 4px solid var(--accent); background: var(--panel); font-size: 1.05rem; line-height: 1.45; }
.source-meta { margin: 4px 0 0; font-size: .85rem; color: var(--muted); }
@media (prefers-color-scheme: dark) { .chart-label { fill: #b7c2bd; } .chart-value { fill: #edf3f0; } }
@media print { .brief-report--designed .cover { padding-top: 8px; } .kpi { background: #fff; } .chart-bar { fill: #146b5c; } }
"""


def _render_with_weasyprint(html: str) -> bytes:
    """Use only the declared local backend and reject every attempted fetch."""

    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError as exc:  # pragma: no cover - the declared dependency is available in CI
        raise BriefReportRenderUnavailable("local PDF renderer is unavailable") from exc
    return WeasyHTML(string=html, url_fetcher=_reject_external_resource).write_pdf()


def render_report(document: BriefDocument, format: Literal["html", "markdown", "pdf"]) -> BriefReportArtifact:
    """Dispatch a pure local rendering operation with no fallback format or egress."""

    if format == "html":
        return render_html(document)
    if format == "markdown":
        return render_markdown(document)
    if format == "pdf":
        return render_pdf(document)
    raise BriefReportRenderError("report format is invalid")


def render_designed_report(document: BriefDocument, format: Literal["html", "pdf"]) -> BriefReportArtifact:
    """Dispatch the richer analytical layout; same facts, no new generation."""

    if format == "html":
        return render_designed_html(document)
    if format == "pdf":
        return render_designed_pdf(document)
    raise BriefReportRenderError("report format is invalid")


class PrivateBriefReportReader:
    """Issue and verify exact owner-bound access to a persisted immutable report.

    Access handles are process-local.  A restart invalidates them, and the
    document is loaded again from the owner-scoped history for every render.
    This deliberately keeps delivery, public URLs and persistent sessions out
    of PA-08.
    """

    def __init__(self, store: BriefDocumentStore, *, access_ttl: timedelta = REPORT_ACCESS_TTL) -> None:
        if type(store) is not BriefDocumentStore:
            raise ValueError("brief document store is required")
        if not isinstance(access_ttl, timedelta) or not timedelta(seconds=1) <= access_ttl <= REPORT_ACCESS_TTL:
            raise ValueError("report access ttl is invalid")
        self._store = store
        self._access_ttl = access_ttl
        self._issued: dict[str, tuple[str, BriefReportAccess]] = {}

    def open(
        self,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        brief_id: str,
        version: int,
        now: datetime | None = None,
    ) -> BriefReportAccess | None:
        """Issue one access handle only after exact persisted owner-bound lookup."""

        owner_ref = brief_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
        )
        moment = _now(now)
        if owner_ref is None:
            return None
        document = self._store.get_persisted_document(
            authenticated_chat_id=authenticated_chat_id,
            authenticated_actor_id=authenticated_actor_id,
            authenticated_owner_chat_id=authenticated_owner_chat_id,
            brief_id=brief_id,
            version=version,
        )
        if document is None or document.owner_ref != owner_ref:
            return None
        access = BriefReportAccess(
            access_ref=secrets.token_urlsafe(32),
            brief_id=document.brief_id,
            version=document.version,
            content_digest=document.content_digest,
            expires_at=moment + self._access_ttl,
        )
        self._issued[access.access_ref] = (owner_ref, access)
        return access

    def render(
        self,
        access: BriefReportAccess,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        format: Literal["html", "markdown", "pdf"],
        now: datetime | None = None,
    ) -> BriefReportArtifact | None:
        """Recheck owner, expiry and exact digest before rendering one local artifact."""

        if format not in {"html", "markdown", "pdf"}:
            return None
        document = self._resolve(access, authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id, now)
        if document is None:
            return None
        return render_report(document, format)

    def preview_share(
        self,
        access: BriefReportAccess,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        recipient_label: str,
        format: Literal["html", "markdown", "pdf"],
        now: datetime | None = None,
    ) -> BriefSharePreview | None:
        """Produce an exact local content/recipient preview without any delivery side effect."""

        recipient = _recipient_label(recipient_label)
        if recipient is None:
            return None
        artifact = self.render(
            access,
            authenticated_chat_id=authenticated_chat_id,
            authenticated_actor_id=authenticated_actor_id,
            authenticated_owner_chat_id=authenticated_owner_chat_id,
            format=format,
            now=now,
        )
        if artifact is None:
            return None
        return BriefSharePreview(recipient, artifact, access.expires_at)

    def _resolve(
        self,
        access: BriefReportAccess,
        chat_id: str | None,
        actor_id: str | None,
        owner_chat_id: str | None,
        now: datetime | None,
    ) -> BriefDocument | None:
        if type(access) is not BriefReportAccess:
            return None
        record = self._issued.get(access.access_ref)
        if record is None or not hmac.compare_digest(record[1].access_ref, access.access_ref) or record[1] != access:
            return None
        moment = _now(now)
        if moment >= access.expires_at:
            self._issued.pop(access.access_ref, None)
            return None
        owner_ref = brief_owner_ref_from_authenticated_private_tuple(chat_id, actor_id, owner_chat_id)
        if owner_ref is None or owner_ref != record[0]:
            return None
        document = self._store.get_persisted_document(
            authenticated_chat_id=chat_id,
            authenticated_actor_id=actor_id,
            authenticated_owner_chat_id=owner_chat_id,
            brief_id=access.brief_id,
            version=access.version,
        )
        if (
            document is None
            or document.owner_ref != owner_ref
            or document.content_digest != access.content_digest
        ):
            return None
        return document


def validate_report_html(html: str) -> dict[str, object]:
    """Reject active/tracked markup and report the static mobile/print contract."""

    if not isinstance(html, str) or len(html) > 1_000_000:
        raise BriefReportRenderError("report html is invalid")
    guard = _StaticHtmlGuard()
    try:
        guard.feed(html)
        guard.close()
    except Exception as exc:
        raise BriefReportRenderError("report html could not be parsed") from exc
    lower = html.lower()
    checks = {
        "private_surface": 'data-surface="private_brief_report"' in lower,
        "viewport": '<meta name="viewport"' in lower,
        "strict_csp": _CSP.lower() in lower,
        "no_active_or_tracking_tags": not guard.forbidden_tags,
        "safe_source_links": not guard.unsafe_links,
        "no_external_styles": "@import" not in lower,
        "responsive_mobile": "@media (max-width: 760px)" in lower,
        "dark_mode": "prefers-color-scheme: dark" in lower,
        "print_page_breaks": "break-inside: avoid" in lower and "@page" in lower,
        "long_url_wrapping": "overflow-wrap: anywhere" in lower,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise BriefReportRenderError("report html safety contract failed: " + ", ".join(failures))
    return {"schema_version": "prm_brief_report_visual_receipt.v1", "status": "passed", "checks": checks}


class _StaticHtmlGuard(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forbidden_tags: set[str] = set()
        self.unsafe_links: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        attributes = {key.casefold(): value for key, value in attrs}
        if lowered in _FORBIDDEN_HTML_TAGS:
            self.forbidden_tags.add(lowered)
        if lowered == "meta" and not _safe_meta(attributes):
            self.forbidden_tags.add("meta")
        if "style" in attributes:
            self.forbidden_tags.add("style-attribute")
        if lowered == "a":
            href = attributes.get("href")
            if href is None or not _safe_https_url(href):
                self.unsafe_links.append(href or "")
        if any(key.startswith("on") for key in attributes):
            self.forbidden_tags.add("event-handler")
        if lowered == "style":
            self._in_style = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style and ("url(" in data.casefold() or "@import" in data.casefold()):
            self.forbidden_tags.add("external-style-resource")


def _require_document(document: BriefDocument) -> None:
    if type(document) is not BriefDocument:
        raise BriefReportRenderError("immutable BriefDocument is required")


def _now(value: datetime | None) -> datetime:
    moment = datetime.now(timezone.utc) if value is None else value
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ValueError("report access time must be timezone-aware")
    return moment.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _period_text(document: BriefDocument) -> str:
    from zoneinfo import ZoneInfo

    tz_name = document.window.timezone or "UTC"
    try:
        tzinfo = ZoneInfo(tz_name)
    except Exception:
        tzinfo = timezone.utc
        tz_name = "UTC"
    start = document.window.start_at.astimezone(tzinfo)
    end = document.window.end_at.astimezone(tzinfo)
    return f"{start:%Y-%m-%d %H:%M} — {end:%Y-%m-%d %H:%M} {tz_name}"


def _display_time(evidence: BriefEvidence) -> str:
    return f"{_iso(evidence.observed_at)} ({evidence.time_kind})"


def _timeline(document: BriefDocument) -> tuple[BriefEvidence, ...]:
    return tuple(sorted(document.evidence, key=lambda item: (_iso(item.observed_at), item.evidence_ref)))


def _markdown_story_or_item_lines(document: BriefDocument) -> list[str]:
    lines: list[str] = []
    sources = document.evidence_by_ref()
    if document.editorial is not None:
        if not document.editorial.stories:
            message = (
                "В проверенной области важных изменений не выделено."
                if document.coverage_manifest.complete
                else "В доступной выборке событий не выделено; это не вывод за весь период."
            )
            return [_markdown_text(message)]
        for number, story in enumerate(document.editorial.stories, start=1):
            lines.extend((
                f"### {number}. {_markdown_text(story.title)}",
                "",
                _markdown_text(story.summary),
                "",
                f"**Объяснение.** {_markdown_text(story.explanation)}",
                "",
                f"**Почему выделено.** {_markdown_text(story.why_selected)}",
            ))
            if story.next_step:
                lines.extend(("", f"**Условный следующий шаг.** {_markdown_text(story.next_step)}"))
            if story.caveat:
                lines.extend(("", f"**Оговорка.** {_markdown_text(story.caveat)}"))
            lines.extend(("", "**Поддерживающие источники.**"))
            for anchor in story.anchors:
                evidence = sources[anchor.evidence_ref]
                lines.append(f"- {_markdown_source(evidence.source_ref)} — {_markdown_text(anchor.quote)}")
            lines.append("")
        return lines
    if not document.items:
        return ["В этой выбранной области нет пунктов для подробного разбора."]
    for section in document.sections:
        lines.extend((f"### {_markdown_text(section.title)}", ""))
        for item in section.items:
            lines.extend((f"#### {_markdown_text(item.title)}", "", _markdown_text(item.summary), ""))
            for evidence_ref in item.evidence_refs:
                evidence = sources[evidence_ref]
                lines.append(f"- Источник: {_markdown_source(evidence.source_ref)}")
            lines.append("")
    return lines


def _story_card_blocks(document: BriefDocument) -> list[str]:
    """One HTML card per editorial story (or per item), for fixed-page packing."""

    sources = document.evidence_by_ref()
    if document.editorial is not None:
        if not document.editorial.stories:
            return []
        blocks: list[str] = []
        for number, story in enumerate(document.editorial.stories, start=1):
            anchors = "".join(
                "<li>{source}<blockquote>{quote}</blockquote></li>".format(
                    source=_html_source_label(sources[anchor.evidence_ref].source_ref), quote=_html_text(anchor.quote),
                )
                for anchor in story.anchors
            )
            next_step = (
                f"<p><strong>Условный следующий шаг.</strong> {_html_text(story.next_step)}</p>" if story.next_step else ""
            )
            caveat = f"<p class=\"caveat\"><strong>Оговорка.</strong> {_html_text(story.caveat)}</p>" if story.caveat else ""
            blocks.append(
                "<article class=\"story\"><p class=\"story-number\">Событие {number}</p><h3>{title}</h3>"
                "<p class=\"takeaway\">{summary}</p><p><strong>Объяснение.</strong> {explanation}</p>"
                "<p><strong>Почему выделено.</strong> {why_selected}</p>{next_step}{caveat}"
                "<h4>Поддерживающие источники</h4><ul>{anchors}</ul></article>".format(
                    number=number,
                    title=_html_text(story.title),
                    summary=_html_text(story.summary),
                    explanation=_html_text(story.explanation),
                    why_selected=_html_text(story.why_selected),
                    next_step=next_step,
                    caveat=caveat,
                    anchors=anchors,
                )
            )
        return blocks
    blocks = []
    for section in document.sections:
        for item in section.items:
            blocks.append(
                "<article class=\"story\"><p class=\"story-number\">{section}</p><h3>{title}</h3>"
                "<p class=\"takeaway\">{summary}</p><ul>{sources}</ul></article>".format(
                    section=_html_text(section.title),
                    title=_html_text(item.title),
                    summary=_html_text(item.summary),
                    sources="".join(
                        f"<li>{_html_source_label(sources[ref].source_ref)}</li>" for ref in item.evidence_refs
                    ),
                )
            )
    return blocks


def _source_card_blocks(document: BriefDocument) -> list[str]:
    return [
        "<article class=\"source-card\"><h3>{title}</h3><p>{summary}</p><p>{source}</p>"
        "<p class=\"source-meta\">{time} · {state}</p></article>".format(
            title=_html_text(evidence.title),
            summary=_html_text(evidence.summary),
            source=_html_source(evidence.source_ref),
            time=_html_text(_display_time(evidence)),
            state=_html_text(evidence.source_state),
        )
        for evidence in document.evidence
    ]


def _reader_source_card_blocks(document: BriefDocument) -> list[str]:
    """Compact reader-facing source rows: title + link, no audit metadata."""

    rows = []
    for index, evidence in enumerate(document.evidence, start=1):
        title = " ".join(str(evidence.title or "").split())
        if len(title) > 110:
            title = (title[:110].rsplit(" ", 1)[0] or title[:110]) + "…"
        rows.append(
            '<div class="source-row"><span class="source-num">{number}</span>'
            '<span class="source-title">{title}</span>'
            '<span class="source-link">{source}</span></div>'.format(
                number=index,
                title=_html_text(title),
                source=_html_source_label(evidence.source_ref),
            )
        )
    return rows


def _html_story_or_item_sections(document: BriefDocument) -> str:
    if document.editorial is not None and not document.editorial.stories:
        message = (
            "В проверенной области важных изменений не выделено."
            if document.coverage_manifest.complete
            else "В доступной выборке событий не выделено; это не вывод за весь период."
        )
        return f"<p class=\"empty\">{_html_text(message)}</p>"
    if not document.items and document.editorial is None:
        return "<p class=\"empty\">В этой выбранной области нет пунктов для подробного разбора.</p>"
    return "".join(_story_card_blocks(document))


def _html_limitations(items: str) -> str:
    return f"<h3>Ограничения</h3><ul>{items}</ul>" if items else ""


def _html_text(value: object) -> str:
    return escape(str(value), quote=False)


def _html_attr(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 500 or any(char.isspace() for char in value):
        return False
    if any(character in value for character in ('<', '>', '"', "'", "\\")):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.casefold() == "https"
            and bool(parsed.netloc)
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _safe_meta(attributes: dict[str, str | None]) -> bool:
    """Allow only static charset/viewport/CSP declarations, never refresh or analytics."""

    if set(attributes) == {"charset"}:
        return attributes["charset"] == "utf-8"
    if set(attributes) == {"name", "content"}:
        return attributes["name"] == "viewport" and attributes["content"] == "width=device-width, initial-scale=1"
    return (
        set(attributes) == {"http-equiv", "content"}
        and attributes["http-equiv"] == "Content-Security-Policy"
        and attributes["content"] == _CSP
    )


def _html_source(value: str) -> str:
    shown = _html_text(value)
    if _safe_https_url(value):
        return f"<a href=\"{_html_attr(value)}\">{shown}</a>"
    return f"<code>{shown}</code>"


def _html_source_label(value: str) -> str:
    """Link with a short, meaningful label so long URLs never break mid-token."""

    from urllib.parse import urlparse

    shown = _html_text(value)
    if not _safe_https_url(value):
        return f"<code>{shown}</code>"
    parsed = urlparse(value)
    host = parsed.hostname or ""
    path = parsed.path.strip("/")
    if host in {"t.me", "telegram.me"} and path:
        label = "@" + path
    elif host:
        label = (host[4:] if host.startswith("www.") else host)
        if path:
            label = f"{label}/{path.split('/')[0]}"
    else:
        label = shown
    if len(label) > 60:
        cut = label[:60].rsplit(" ", 1)[0] or label[:60]
        label = cut + "…"
    return f"<a href=\"{_html_attr(value)}\">{_html_text(label or shown)}</a>"


def _markdown_text(value: object) -> str:
    result = str(value).replace("\\", "\\\\").replace("`", "\\`")
    result = result.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for marker in ("*", "_", "[", "]", "(", ")", "#", "+", "!", "|"):
        result = result.replace(marker, "\\" + marker)
    return result


def _markdown_table(value: object) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_source(value: str) -> str:
    # An allowed HTTPS source remains a portable clickable link. Anything else
    # stays inert code so malformed stored data cannot become active Markdown.
    if _safe_https_url(value):
        return f"[{_markdown_text(value)}](<{value}>)"
    return "`" + value.replace("`", "\\`").replace("<", "&lt;").replace(">", "&gt;") + "`"


def _recipient_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    clean = " ".join(value.split())
    if not clean or len(clean) > 200 or any(ord(character) < 32 for character in clean):
        return None
    return clean


def _reject_external_resource(url: str, *args: object, **kwargs: object) -> object:
    del url, args, kwargs
    raise BriefReportRenderUnavailable("external report resource is blocked")


def _render_fallback_pdf(document: BriefDocument) -> bytes:
    """Build a small Unicode PDF when the installed HTML-to-PDF bridge is broken."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:  # pragma: no cover - required by WeasyPrint
        raise BriefReportRenderUnavailable("local Unicode PDF fallback is unavailable") from exc
    font_path = _fallback_font_path()
    if font_path is None:
        raise BriefReportRenderUnavailable("local Unicode PDF font is unavailable")
    try:
        font_data = font_path.read_bytes()
        font = TTFont(str(font_path), recalcBBoxes=False, recalcTimestamp=False)
        cmap = font.getBestCmap()
        glyph_order = font.getGlyphOrder()
        glyph_ids = {name: index for index, name in enumerate(glyph_order)}
        units_per_em = int(font["head"].unitsPerEm)
        widths = {
            glyph_ids[name]: max(1, round(font["hmtx"].metrics[name][0] * 1000 / units_per_em))
            for name in set(cmap.values())
            if name in glyph_ids
        }
    except Exception as exc:
        raise BriefReportRenderUnavailable("local Unicode PDF fallback could not load its font") from exc
    question_name = cmap.get(ord("?"))
    if question_name is None or question_name not in glyph_ids:
        raise BriefReportRenderUnavailable("local Unicode PDF fallback has no replacement glyph")
    replacement_gid = glyph_ids[question_name]
    replacement_width = widths.get(replacement_gid, 500)

    glyph_unicode: dict[int, str] = {}

    def glyph_id(character: str) -> int:
        name = cmap.get(ord(character))
        glyph = glyph_ids.get(name, replacement_gid)
        glyph_unicode.setdefault(glyph, character if glyph != replacement_gid else "?")
        return glyph

    def encoded(text: str) -> str:
        return "".join(f"{glyph_id(character):04X}" for character in text)

    def text_width(text: str, size: float) -> float:
        return sum(widths.get(glyph_id(character), replacement_width) * size / 1000 for character in text)

    pages: list[tuple[list[str], list[tuple[float, float, float, float, str]]]] = []
    commands: list[str] = []
    page_links: list[tuple[float, float, float, float, str]] = []
    y = 800.0

    def new_page() -> None:
        nonlocal commands, page_links, y
        if commands:
            pages.append((commands, page_links))
        commands = ["0.08 0.42 0.36 rg", "36 814 523 3 re f", "0.12 0.15 0.15 rg"]
        page_links = []
        y = 790.0

    def put(
        text: str,
        *,
        size: float,
        color: tuple[float, float, float],
        gap: float = 0.0,
        link: str | None = None,
    ) -> None:
        nonlocal y
        for line in _pdf_wrap(text, size=size, maximum=523.0, width=text_width):
            line_height = size * 1.42
            if y - line_height < 42:
                new_page()
            commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg")
            commands.append(f"BT /F1 {size:.2f} Tf 1 0 0 1 36 {y:.2f} Tm <{encoded(line)}> Tj ET")
            if link is not None and _safe_https_url(link):
                page_links.append((36.0, y - size * 0.32, min(559.0, 36.0 + text_width(line, size)), y + size, link))
            y -= line_height
        y -= gap

    new_page()
    for style, text, link in _pdf_text_lines(document):
        if style == "title":
            put(text, size=21, color=(0.06, 0.24, 0.21), gap=9, link=link)
        elif style == "heading":
            put(text, size=14, color=(0.06, 0.36, 0.31), gap=4, link=link)
        elif style == "subheading":
            put(text, size=11.5, color=(0.12, 0.15, 0.15), gap=2, link=link)
        elif style == "caveat":
            put(text, size=9.6, color=(0.43, 0.23, 0.04), gap=3, link=link)
        else:
            put(text, size=9.6, color=(0.12, 0.15, 0.15), gap=2, link=link)
    if commands:
        pages.append((commands, page_links))

    numbered_pages = []
    for number, (page_commands, links) in enumerate(pages, start=1):
        footer = f"Страница {number} / {len(pages)}"
        page_commands.extend((
            "0.35 0.40 0.39 rg",
            f"BT /F1 8 Tf 1 0 0 1 490 25 Tm <{encoded(footer)}> Tj ET",
        ))
        numbered_pages.append(("\n".join(page_commands).encode("ascii"), links))

    return _build_unicode_pdf(
        pages=numbered_pages,
        font_data=font_data,
        glyph_unicode=glyph_unicode,
        widths=widths,
        units_per_em=units_per_em,
    )


def _fallback_font_path() -> Path | None:
    for value in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
    ):
        candidate = Path(value)
        if candidate.is_file():
            return candidate
    return None


def _pdf_text_lines(document: BriefDocument) -> list[tuple[str, str, str | None]]:
    """Flatten all saved report content into labelled print lines without inference."""

    lines: list[tuple[str, str, str | None]] = [
        ("title", document.topic, None),
        ("body", f"Версия: {document.brief_id} v{document.version}", None),
        ("body", f"Идентичность содержимого: {document.content_digest}", None),
        ("body", f"Период: {_period_text(document)}", None),
        ("heading", "События и объяснения", None),
    ]
    sources = document.evidence_by_ref()
    if document.editorial is not None:
        if not document.editorial.stories:
            lines.append(("body", "В выбранной области событий не выделено; покрытие указано ниже.", None))
        for number, story in enumerate(document.editorial.stories, start=1):
            lines.extend((
                ("subheading", f"{number}. {story.title}", None),
                ("body", story.summary, None),
                ("body", f"Объяснение: {story.explanation}", None),
                ("body", f"Почему выделено: {story.why_selected}", None),
            ))
            if story.next_step:
                lines.append(("body", f"Условный следующий шаг: {story.next_step}", None))
            if story.caveat:
                lines.append(("caveat", f"Оговорка: {story.caveat}", None))
            for anchor in story.anchors:
                source_ref = sources[anchor.evidence_ref].source_ref
                lines.append(("body", f"Источник: {source_ref}", source_ref))
                lines.append(("body", f"Цитата: {anchor.quote}", None))
    else:
        for section in document.sections:
            lines.append(("subheading", section.title, None))
            for item in section.items:
                lines.extend((("body", item.title, None), ("body", item.summary, None)))
                lines.extend(("body", f"Источник: {sources[ref].source_ref}", sources[ref].source_ref) for ref in item.evidence_refs)
    lines.append(("heading", "Временная линия источников", None))
    for evidence in _timeline(document):
        lines.extend((("subheading", f"{_display_time(evidence)} — {evidence.title}", None), ("body", evidence.summary, None)))
    lines.append(("heading", "Покрытие", None))
    for source in document.coverage_manifest.sources:
        suffix = f"; ограничение: {source.reason}" if source.reason else ""
        lines.append(("body", f"{source.source_ref}: {source.state}{suffix}", None))
    if document.coverage_manifest.limitations:
        lines.append(("body", "Ограничения: " + ", ".join(document.coverage_manifest.limitations), None))
    lines.append(("heading", "Источники", None))
    for evidence in document.evidence:
        lines.extend((
            ("subheading", evidence.title, None),
            ("body", evidence.summary, None),
            ("body", f"URL: {evidence.source_ref}", evidence.source_ref),
            ("body", f"Время: {_display_time(evidence)}; состояние: {evidence.source_state}; отношение к периоду: {evidence.period_relation}", None),
        ))
    return lines


def _pdf_wrap(
    text: str,
    *,
    size: float,
    maximum: float,
    width: Callable[[str, float], float],
) -> tuple[str, ...]:
    """Wrap at words first, then within an overlong URL without dropping characters."""

    clean = " ".join(str(text).split()) or "—"
    result: list[str] = []
    current = ""
    for word in clean.split(" "):
        candidate = word if not current else current + " " + word
        if width(candidate, size) <= maximum:
            current = candidate
            continue
        if current:
            result.append(current)
            current = ""
        while word and width(word, size) > maximum:
            cut = 1
            while cut < len(word) and width(word[: cut + 1], size) <= maximum:
                cut += 1
            result.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        result.append(current)
    return tuple(result)


def _build_unicode_pdf(
    *,
    pages: list[tuple[bytes, list[tuple[float, float, float, float, str]]]],
    font_data: bytes,
    glyph_unicode: dict[int, str],
    widths: dict[int, int],
    units_per_em: int,
) -> bytes:
    """Write a minimal Type0/CIDFont PDF with an embedded Unicode TrueType font."""

    del units_per_em
    page_count = len(pages)
    page_object_start = 8
    content_object_start = page_object_start + page_count
    annotation_object_start = content_object_start + page_count
    objects: dict[int, bytes] = {}
    kids = " ".join(f"{page_object_start + index} 0 R" for index in range(page_count))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii")
    objects[3] = b"<< /Type /Font /Subtype /Type0 /BaseFont /DejaVuSans /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 7 0 R >>"
    width_array = " ".join(f"{gid} [{widths.get(gid, 500)}]" for gid in sorted(glyph_unicode))
    objects[4] = (
        "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /DejaVuSans "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        "/FontDescriptor 5 0 R /DW 1000 /W [" + width_array + "] /CIDToGIDMap /Identity >>"
    ).encode("ascii")
    objects[5] = b"<< /Type /FontDescriptor /FontName /DejaVuSans /Flags 32 /FontBBox [-1021 -463 1793 1232] /ItalicAngle 0 /Ascent 928 /Descent -236 /CapHeight 729 /StemV 80 /FontFile2 6 0 R >>"
    compressed_font = zlib.compress(font_data, level=9)
    objects[6] = _pdf_stream(compressed_font, extra=f"/Length1 {len(font_data)} /Filter /FlateDecode")
    objects[7] = _pdf_stream(_to_unicode_cmap(glyph_unicode), extra="")
    next_annotation = annotation_object_start
    for index, (content, links) in enumerate(pages):
        page_number = page_object_start + index
        content_number = content_object_start + index
        annotation_refs = []
        for left, bottom, right, top, source_ref in links:
            annotation_refs.append(f"{next_annotation} 0 R")
            objects[next_annotation] = (
                "<< /Type /Annot /Subtype /Link /Rect "
                f"[{left:.2f} {bottom:.2f} {right:.2f} {top:.2f}] /Border [0 0 0] "
                f"/A << /S /URI /URI {_pdf_uri(source_ref)} >> >>"
            ).encode("ascii")
            next_annotation += 1
        annotations = " /Annots [" + " ".join(annotation_refs) + "]" if annotation_refs else ""
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R{annotations} >>"
        ).encode("ascii")
        objects[content_number] = _pdf_stream(content, extra="")
    buffer = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number in range(1, max(objects) + 1):
        offsets.append(len(buffer))
        buffer.extend(f"{number} 0 obj\n".encode("ascii"))
        buffer.extend(objects[number])
        buffer.extend(b"\nendobj\n")
    xref_at = len(buffer)
    buffer.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    buffer.extend(b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:]))
    buffer.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
    return bytes(buffer)


def _pdf_stream(data: bytes, *, extra: str) -> bytes:
    suffix = (" " + extra) if extra else ""
    return f"<< /Length {len(data)}{suffix} >>\nstream\n".encode("ascii") + data + b"\nendstream"


def _pdf_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_uri(value: str) -> str:
    """Encode an annotation URI without losing valid Unicode source identity."""

    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return "<FEFF" + value.encode("utf-16-be").hex().upper() + ">"
    return "(" + _pdf_literal(value) + ")"


def _to_unicode_cmap(glyph_unicode: dict[int, str]) -> bytes:
    mappings = []
    for glyph, character in sorted(glyph_unicode.items()):
        destination = character.encode("utf-16-be").hex().upper()
        mappings.append(f"<{glyph:04X}> <{destination}>")
    parts = [
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n",
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n",
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n",
    ]
    for start in range(0, len(mappings), 100):
        group = mappings[start:start + 100]
        parts.append(f"{len(group)} beginbfchar\n" + "\n".join(group) + "\nendbfchar\n")
    parts.append("endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n")
    return "".join(parts).encode("ascii")


def _stylesheet() -> str:
    return """
@page { size: A4; margin: 22mm 13mm 20mm; @top-left { content: string(brieftitle); font-size: 9pt; color: #4f5858; } @top-center { content: string(briefsection); font-size: 8.5pt; color: #4f5858; } @top-right { content: string(briefperiod); font-size: 8.5pt; color: #4f5858; } @bottom-center { content: "Страница " counter(page) " / " counter(pages); font-size: 8.5pt; color: #4f5858; } }
@page :first { @top-left { content: none; } @top-center { content: none; } @top-right { content: none; } }
:root { color-scheme: light dark; --bg: #f5f5f0; --panel: #ffffff; --ink: #1e2525; --muted: #4f5858; --line: #cbd2cc; --accent: #146b5c; --caveat: #7b4a13; }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.brief-report { width: min(980px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 52px; overflow-wrap: anywhere; }
.hero, .brief-report > section { border-bottom: 1px solid var(--line); padding: 24px 0; }
.hero { padding-top: 0; }
.eyebrow, .story-number { margin: 0 0 7px; color: var(--accent); font-size: .76rem; font-weight: 760; letter-spacing: .04em; text-transform: uppercase; }
h1, h2, h3, h4 { line-height: 1.18; break-after: avoid; }
h1 { max-width: 20ch; margin: 0 0 12px; font-size: clamp(2rem, 7vw, 3.6rem); string-set: brieftitle content(text); }
h2 { margin: 0 0 18px; font-size: clamp(1.45rem, 5vw, 2rem); string-set: briefsection content(text); }
h3 { margin: 0 0 8px; font-size: 1.15rem; }
h4 { margin: 18px 0 8px; font-size: 1rem; }
p, li { orphans: 2; widows: 2; }
p, li, td, th, dd, code, a, blockquote { overflow-wrap: anywhere; }
h2 + div, h2 + ol, h2 + p, h2 + svg, h2 + .table-wrap, h2 + .source-grid { break-before: avoid; }
.brief-report > section:last-of-type { border-bottom: 0; padding-bottom: 0; }
.period { color: var(--muted); string-set: briefperiod content(text); }
.identity, .source-card dl { color: var(--muted); }
.identity { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 18px 0 0; }
.identity dt, .source-card dt { font-weight: 700; }
.identity dd, .source-card dd { margin: 0; }
.story { margin: 14px 0; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); font-size: .97rem; }
.source-card { break-inside: avoid; margin: 14px 0; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); font-size: .97rem; }
.story .takeaway { margin: 0 0 14px; font-size: 1.1rem; font-weight: 620; }
.caveat { border-left: 4px solid var(--caveat); padding-left: 12px; }
blockquote { margin: 7px 0; padding-left: 12px; border-left: 2px solid var(--line); color: var(--muted); }
.timeline { display: grid; gap: 14px; margin: 0; padding: 0; list-style: none; }
.timeline li { display: grid; grid-template-columns: minmax(10rem, .45fr) 1fr; gap: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--line); break-inside: avoid; }
.timeline p { margin: 4px 0 8px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { background: color-mix(in srgb, var(--accent) 10%, var(--panel)); }
.source-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
a { color: var(--accent); }
@media (prefers-color-scheme: dark) { :root { --bg: #121716; --panel: #1c2422; --ink: #edf3f0; --muted: #b7c2bd; --line: #43514c; --accent: #7dd7c1; --caveat: #ffc47b; } }
@media (max-width: 760px) { .brief-report { width: min(100% - 20px, 680px); padding: 18px 0 32px; } .hero, .brief-report > section { padding: 18px 0; } .story, .source-card { padding: 14px; } .timeline li { grid-template-columns: 1fr; gap: 4px; } .identity { grid-template-columns: 1fr; gap: 1px; } }
@media print { body { background: #fff; color: #111; } .brief-report { width: auto; padding: 0; } .story, .source-card { background: #fff; } a { color: #111; text-decoration: underline; } }
"""
