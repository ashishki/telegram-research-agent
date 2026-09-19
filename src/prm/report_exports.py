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
import secrets
from typing import Callable, Literal
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
            source=_html_text(item.source_ref),
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
  <section aria-labelledby="sources-heading"><p class="eyebrow">Проверяемые основания</p><h2 id="sources-heading">Источники</h2><div class="source-grid">{source_rows}</div></section>
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
        from weasyprint import HTML as WeasyHTML
    except ImportError as exc:  # pragma: no cover - the declared dependency is available in CI
        raise BriefReportRenderUnavailable("local PDF renderer is unavailable") from exc
    try:
        body = WeasyHTML(string=str(html_artifact.body), url_fetcher=_reject_external_resource).write_pdf()
    except Exception:
        body = _render_fallback_pdf(document)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise BriefReportRenderUnavailable("local PDF renderer returned an invalid artifact")
    return BriefReportArtifact("pdf", "application/pdf", body, html_artifact.identity)


def render_report(document: BriefDocument, format: Literal["html", "markdown", "pdf"]) -> BriefReportArtifact:
    """Dispatch a pure local rendering operation with no fallback format or egress."""

    if format == "html":
        return render_html(document)
    if format == "markdown":
        return render_markdown(document)
    if format == "pdf":
        return render_pdf(document)
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
    return (
        f"{document.window.start_at.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC} — "
        f"{document.window.end_at.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC}; {document.window.timezone}"
    )


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


def _html_story_or_item_sections(document: BriefDocument) -> str:
    sources = document.evidence_by_ref()
    if document.editorial is not None:
        if not document.editorial.stories:
            message = (
                "В проверенной области важных изменений не выделено."
                if document.coverage_manifest.complete
                else "В доступной выборке событий не выделено; это не вывод за весь период."
            )
            return f"<p class=\"empty\">{_html_text(message)}</p>"
        blocks = []
        for number, story in enumerate(document.editorial.stories, start=1):
            anchors = "".join(
                "<li>{source}<blockquote>{quote}</blockquote></li>".format(
                    source=_html_source(sources[anchor.evidence_ref].source_ref), quote=_html_text(anchor.quote),
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
        return "".join(blocks)
    if not document.items:
        return "<p class=\"empty\">В этой выбранной области нет пунктов для подробного разбора.</p>"
    blocks = []
    for section in document.sections:
        items = "".join(
            "<article class=\"story\"><h3>{title}</h3><p class=\"takeaway\">{summary}</p>"
            "<ul>{sources}</ul></article>".format(
                title=_html_text(item.title),
                summary=_html_text(item.summary),
                sources="".join(f"<li>{_html_source(sources[ref].source_ref)}</li>" for ref in item.evidence_refs),
            )
            for item in section.items
        )
        blocks.append(f"<section class=\"section\"><h3>{_html_text(section.title)}</h3>{items}</section>")
    return "".join(blocks)


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


def _markdown_text(value: object) -> str:
    result = str(value).replace("\\", "\\\\").replace("`", "\\`")
    result = result.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for marker in ("*", "_", "[", "]", "(", ")", "#", "+", "!", "|"):
        result = result.replace(marker, "\\" + marker)
    return result


def _markdown_table(value: object) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_source(value: str) -> str:
    # Backticks prevent a malformed source value from becoming Markdown/HTML;
    # the artifact identity retains the exact ordered source references.
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

    pages: list[bytes] = []
    commands: list[str] = []
    y = 800.0

    def new_page() -> None:
        nonlocal commands, y
        if commands:
            pages.append("\n".join(commands).encode("ascii"))
        commands = ["0.08 0.42 0.36 rg", "36 814 523 3 re f", "0.12 0.15 0.15 rg"]
        y = 790.0

    def put(text: str, *, size: float, color: tuple[float, float, float], gap: float = 0.0) -> None:
        nonlocal y
        for line in _pdf_wrap(text, size=size, maximum=523.0, width=text_width):
            line_height = size * 1.42
            if y - line_height < 42:
                new_page()
            commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg")
            commands.append(f"BT /F1 {size:.2f} Tf 1 0 0 1 36 {y:.2f} Tm <{encoded(line)}> Tj ET")
            y -= line_height
        y -= gap

    new_page()
    for style, text in _pdf_text_lines(document):
        if style == "title":
            put(text, size=21, color=(0.06, 0.24, 0.21), gap=9)
        elif style == "heading":
            put(text, size=14, color=(0.06, 0.36, 0.31), gap=4)
        elif style == "subheading":
            put(text, size=11.5, color=(0.12, 0.15, 0.15), gap=2)
        elif style == "caveat":
            put(text, size=9.6, color=(0.43, 0.23, 0.04), gap=3)
        else:
            put(text, size=9.6, color=(0.12, 0.15, 0.15), gap=2)
    if commands:
        pages.append("\n".join(commands).encode("ascii"))

    return _build_unicode_pdf(
        pages=pages,
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


def _pdf_text_lines(document: BriefDocument) -> list[tuple[str, str]]:
    """Flatten all saved report content into labelled print lines without inference."""

    lines: list[tuple[str, str]] = [
        ("title", document.topic),
        ("body", f"Версия: {document.brief_id} v{document.version}"),
        ("body", f"Идентичность содержимого: {document.content_digest}"),
        ("body", f"Период: {_period_text(document)}"),
        ("heading", "События и объяснения"),
    ]
    sources = document.evidence_by_ref()
    if document.editorial is not None:
        if not document.editorial.stories:
            lines.append(("body", "В выбранной области событий не выделено; покрытие указано ниже."))
        for number, story in enumerate(document.editorial.stories, start=1):
            lines.extend((
                ("subheading", f"{number}. {story.title}"),
                ("body", story.summary),
                ("body", f"Объяснение: {story.explanation}"),
                ("body", f"Почему выделено: {story.why_selected}"),
            ))
            if story.next_step:
                lines.append(("body", f"Условный следующий шаг: {story.next_step}"))
            if story.caveat:
                lines.append(("caveat", f"Оговорка: {story.caveat}"))
            for anchor in story.anchors:
                lines.append(("body", f"Источник: {sources[anchor.evidence_ref].source_ref}"))
                lines.append(("body", f"Цитата: {anchor.quote}"))
    else:
        for section in document.sections:
            lines.append(("subheading", section.title))
            for item in section.items:
                lines.extend((("body", item.title), ("body", item.summary)))
                lines.extend(("body", f"Источник: {sources[ref].source_ref}") for ref in item.evidence_refs)
    lines.append(("heading", "Временная линия источников"))
    for evidence in _timeline(document):
        lines.extend((("subheading", f"{_display_time(evidence)} — {evidence.title}"), ("body", evidence.summary)))
    lines.append(("heading", "Покрытие"))
    for source in document.coverage_manifest.sources:
        suffix = f"; ограничение: {source.reason}" if source.reason else ""
        lines.append(("body", f"{source.source_ref}: {source.state}{suffix}"))
    if document.coverage_manifest.limitations:
        lines.append(("body", "Ограничения: " + ", ".join(document.coverage_manifest.limitations)))
    lines.append(("heading", "Источники"))
    for evidence in document.evidence:
        lines.extend((
            ("subheading", evidence.title),
            ("body", evidence.summary),
            ("body", f"URL: {evidence.source_ref}"),
            ("body", f"Время: {_display_time(evidence)}; состояние: {evidence.source_state}; отношение к периоду: {evidence.period_relation}"),
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
    pages: list[bytes],
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
    for index, content in enumerate(pages):
        page_number = page_object_start + index
        content_number = content_object_start + index
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
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
@page { size: A4; margin: 15mm 13mm; }
:root { color-scheme: light dark; --bg: #f5f5f0; --panel: #ffffff; --ink: #1e2525; --muted: #586161; --line: #cbd2cc; --accent: #146b5c; --caveat: #7b4a13; }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.brief-report { width: min(980px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 52px; overflow-wrap: anywhere; }
.hero, .brief-report > section { border-bottom: 1px solid var(--line); padding: 24px 0; }
.hero { padding-top: 0; }
.eyebrow, .story-number { margin: 0 0 7px; color: var(--accent); font-size: .76rem; font-weight: 760; letter-spacing: .04em; text-transform: uppercase; }
h1, h2, h3, h4 { line-height: 1.18; }
h1 { max-width: 20ch; margin: 0 0 12px; font-size: clamp(2rem, 7vw, 3.6rem); }
h2 { margin: 0 0 18px; font-size: clamp(1.45rem, 5vw, 2rem); }
h3 { margin: 0 0 8px; font-size: 1.15rem; }
h4 { margin: 18px 0 8px; font-size: .94rem; }
p, li, td, th, dd, code, a, blockquote { overflow-wrap: anywhere; word-break: break-word; }
.period, .identity, .source-card dl { color: var(--muted); }
.identity { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 18px 0 0; }
.identity dt, .source-card dt { font-weight: 700; }
.identity dd, .source-card dd { margin: 0; }
.story, .source-card { break-inside: avoid; margin: 14px 0; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); }
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
