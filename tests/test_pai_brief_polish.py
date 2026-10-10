"""Source identity survives mobile/print presentation improvements."""
from html.parser import HTMLParser
import re
from prm.report_exports import render_designed_html,render_html,render_markdown,render_paginated_pdf
from prm.briefs import render_brief_document
from tests.test_assistant_report_exports import _editorial_document


def test_every_chat_finding_keeps_all_anchored_sources_and_clear_counts():
    document=_editorial_document();text=render_brief_document(document,view='telegram')
    assert all(item.source_ref in text for item in document.evidence)
    assert 'Проверено подключений: 1 из 1' in text and 'использовано материалов: 2' in text
    assert 'в пределах выбранных источников' in text


def test_mobile_has_legible_chart_values_and_stacked_coverage_without_changing_identity():
    document=_editorial_document();artifact=render_designed_html(document);body=str(artifact.body)
    assert 'class="chart-values"' in body and '2 материалов' in body
    assert 'data-label="Источник"' in body and 'content: attr(data-label)' in body
    assert '.chart, .hbar { display: none; }' in body and 'font-size: 1rem' in body
    assert 'data-print-period=' in body and 'content: string(briefperiodshort)' in body
    assert '<rect fill="#146b5c"' in body
    assert artifact.identity==render_paginated_pdf(document).identity
    assert set(artifact.identity.source_refs)==set(item.source_ref for item in document.evidence)


def test_markdown_identity_is_retained_in_hidden_metadata_and_plain_version_is_readable():
    document=_editorial_document();body=str(render_markdown(document).body)
    assert document.content_digest in body and '<!-- brief ' in body
    visible=body.split('<!-- brief ',1)[0]
    assert document.content_digest not in visible and document.brief_id not in visible
    assert 'Покрытие: полное в выбранной области' in visible


def test_equal_source_title_and_summary_are_not_repeated_inside_card():
    from dataclasses import replace
    document=_editorial_document()
    evidence=tuple(replace(item,title=item.summary) for item in document.evidence)
    document=replace(document,evidence=evidence)
    body=str(render_designed_html(document).body)
    cards=re.findall(r'<article class="source-card">(.*?)</article>',body,re.S)
    assert len(cards)==len(evidence)
    for card,item in zip(cards,evidence):assert card.count(item.summary)==1
