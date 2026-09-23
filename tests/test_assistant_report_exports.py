from __future__ import annotations

from dataclasses import replace
import re

import pytest

from prm.brief_editorial import BriefEditorial
from prm.briefs import BriefBuildRequest, BriefWindow, CoverageSource, build_brief_document
from prm.report_exports import BriefReportRenderError, render_html, render_markdown, render_pdf, validate_report_html


def _window() -> BriefWindow:
    return BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at="2026-10-19T00:00:00+02:00",
        end_at="2026-10-26T00:00:00+01:00",
        generated_at="2026-10-26T01:15:00+01:00",
    )


def _source(identifier: str, source_url: str, title: str, summary: str, posted_at: str) -> dict[str, object]:
    return {
        "local_archive_provenance": True,
        "evidence_id": identifier,
        "source_url": source_url,
        "title": title,
        "support_span": summary,
        "posted_at": posted_at,
        "topics": ("AI",),
        "importance": "high",
        "urgent": False,
    }


def _editorial_document():
    long_url = "https://example.test/source/" + "a" * 430
    request = BriefBuildRequest(
        topic="Недельный обзор ИИ",
        window=_window(),
        coverage=(CoverageSource("telegram:archive", "checked"),),
        evidence=(
            _source(
                "first", long_url, "Первый сигнал",
                "Первый источник подтверждает изменение режима обработки отчётов.",
                "2026-10-21T10:00:00+02:00",
            ),
            _source(
                "second", "https://example.test/кириллица", "Второй сигнал",
                "Второй источник описывает ограничение и сохраняет исходную оговорку.",
                "2026-10-23T10:00:00+02:00",
            ),
        ),
    )
    base = build_brief_document(request)
    editorial = BriefEditorial.from_dict(
        {
            "stories": [{
                "title": "Отчёт получил проверяемую подробную форму",
                "summary": "Источники описывают изменение режима обработки отчётов и его ограничение.",
                "explanation": "Первый источник подтверждает изменение режима обработки отчётов, а второй сохраняет исходную оговорку.",
                "plain_explanation": "Отчёт стал подробнее, но его ограничения остаются видимыми.",
                "why_selected": "Изменение влияет на то, как читать и проверять недельный отчёт.",
                "next_step": "Если это важно для текущей работы, сверить оба источника перед применением.",
                "caveat": "Источники описывают изменение, но не подтверждают результат вне этой выборки.",
                "anchors": [
                    {"evidence_ref": "evidence_first", "quote": "Первый источник подтверждает изменение режима обработки отчётов."},
                    {"evidence_ref": "evidence_second", "quote": "Второй источник описывает ограничение и сохраняет исходную оговорку."},
                ],
            }],
            "omitted_refs": [],
        },
        base.evidence,
    )
    return build_brief_document(replace(request, editorial=editorial))


def test_html_pdf_and_markdown_preserve_one_exact_editorial_document() -> None:
    document = _editorial_document()

    markdown = render_markdown(document)
    html = render_html(document)
    pdf = render_pdf(document)

    assert markdown.identity == html.identity == pdf.identity
    assert markdown.identity.brief_id == document.brief_id
    assert markdown.identity.version == document.version
    assert markdown.identity.content_digest == document.content_digest
    assert markdown.identity.source_refs == tuple(item.source_ref for item in document.evidence)
    assert pdf.media_type == "application/pdf"
    assert isinstance(pdf.body, bytes) and pdf.body.startswith(b"%PDF-")

    assert isinstance(markdown.body, str) and isinstance(html.body, str)
    for value in (
        "Отчёт получил проверяемую подробную форму",
        "Источники описывают изменение режима обработки отчётов и его ограничение.",
        "Источники описывают изменение, но не подтверждают результат вне этой выборки.",
        document.content_digest,
        document.evidence[0].source_ref,
        document.evidence[1].source_ref,
    ):
        assert value in markdown.body
        assert value in html.body
    assert "Временная линия источников" in markdown.body
    assert "Временная линия источников" in html.body
    assert "Покрытие" in markdown.body and "<table>" in html.body
    assert f"[{document.evidence[0].source_ref}](<{document.evidence[0].source_ref}>)" in markdown.body
    assert f"[{document.evidence[1].source_ref}](<{document.evidence[1].source_ref}>)" in markdown.body
    assert validate_report_html(html.body)["status"] == "passed"


def test_fallback_pdf_keeps_unicode_text_links_long_urls_and_page_numbers(monkeypatch) -> None:
    document = _editorial_document()

    def unavailable(_: str) -> bytes:
        raise RuntimeError("synthetic local PDF backend failure")

    monkeypatch.setattr("prm.report_exports._render_with_weasyprint", unavailable)
    pdf = render_pdf(document)

    assert isinstance(pdf.body, bytes)
    assert b"/ToUnicode" in pdf.body
    assert b"/Annots [" in pdf.body
    for source_ref in pdf.identity.source_refs:
        if source_ref.isascii():
            assert f"/URI ({source_ref})".encode("ascii") in pdf.body
        else:
            assert ("FEFF" + source_ref.encode("utf-16-be").hex().upper()).encode("ascii") in pdf.body
    extracted = _fallback_pdf_text(pdf.body)
    assert "Отчёт получил проверяемую подробную форму" in extracted
    assert document.evidence[0].source_ref in extracted
    assert "Страница 1 /" in extracted


def test_fallback_pdf_numbers_every_page_of_a_multi_page_report(monkeypatch) -> None:
    evidence = tuple(
        _source(
            f"page-{number}",
            f"https://example.test/multi-page/{number}",
            f"Проверяемый источник {number}",
            "Подтверждение для проверки разрыва страниц. " * 25,
            f"2026-10-{number:02d}T10:00:00+02:00",
        )
        for number in range(1, 21)
    )
    document = build_brief_document(
        BriefBuildRequest(
            topic="Многостраничный частный отчёт",
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=evidence,
        )
    )

    def unavailable(_: str) -> bytes:
        raise RuntimeError("synthetic local PDF backend failure")

    monkeypatch.setattr("prm.report_exports._render_with_weasyprint", unavailable)
    pdf = render_pdf(document)
    extracted = _fallback_pdf_text(pdf.body)
    labels = re.findall(r"Страница (\d+) / (\d+)", extracted)

    assert labels
    total = int(labels[0][1])
    assert total > 1
    assert labels == [(str(number), str(total)) for number in range(1, total + 1)]
    assert document.evidence[-1].source_ref in extracted


def _fallback_pdf_text(pdf: bytes) -> str:
    """Read this fallback's explicit CID text streams via its ToUnicode map."""

    cmap = {
        int(source, 16): bytes.fromhex(destination.decode("ascii")).decode("utf-16-be")
        for source, destination in re.findall(rb"<([0-9A-F]{4})> <([0-9A-F]+)>", pdf)
        if len(destination) % 4 == 0
    }
    lines = []
    for stream in re.findall(rb"stream\n(.*?)\nendstream", pdf, flags=re.DOTALL):
        if b" Tj" not in stream:
            continue
        for payload in re.findall(rb"<([0-9A-F]+)> Tj", stream):
            lines.append("".join(cmap.get(int(payload[index:index + 4], 16), "?") for index in range(0, len(payload), 4)))
    return "".join(lines)


def test_source_text_is_escaped_and_static_html_rejects_active_or_tracking_markup() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="<script>не исполнять</script>",
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(
                _source(
                    "unsafe", "https://example.test/source/unsafe?first=1&second=2",
                    "<img src=x onerror=alert(1)>", "Текст <script> остаётся данными, а не инструкцией.",
                    "2026-10-22T10:00:00+02:00",
                ),
            ),
        )
    )

    html = render_html(document)
    markdown = render_markdown(document)

    assert isinstance(html.body, str) and isinstance(markdown.body, str)
    assert "<script>" not in html.body.casefold()
    assert "<img " not in html.body.casefold()
    assert "&lt;script&gt;" in html.body
    assert "&lt;script&gt;" in markdown.body
    assert "<script>" not in markdown.body.casefold()
    assert "Content-Security-Policy" in html.body
    assert "connect-src 'none'" in html.body
    assert "@import" not in html.body
    assert "<img" not in html.body.casefold()

    with pytest.raises(BriefReportRenderError, match="no_active_or_tracking_tags"):
        validate_report_html(str(html.body).replace("</body>", "<script>bad()</script></body>"))
    with pytest.raises(BriefReportRenderError, match="safe_source_links"):
        validate_report_html(str(html.body).replace("https://example.test", "javascript:alert(1)", 1))


def test_pdf_layout_has_running_header_and_orphan_control() -> None:
    html = render_html(_editorial_document())
    body = str(html.body)
    # Running header/footer: title and period repeat on every printed page.
    assert "string-set: brieftitle content(text)" in body
    assert "string-set: briefperiod content(text)" in body
    assert "string-set: briefsection content(text)" in body
    assert "content: string(brieftitle)" in body
    assert "content: string(briefperiod)" in body
    assert "content: string(briefsection)" in body
    # Orphan/widow and heading-break control so a heading never hangs alone.
    assert "break-after: avoid" in body
    assert "orphans: 2" in body
    assert "widows: 2" in body
