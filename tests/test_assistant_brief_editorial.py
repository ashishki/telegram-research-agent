"""Synthetic content-path cases; these are not a live-model quality receipt."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from prm.application import PersonalResearchAssistant
from prm.brief_editorial import BriefEditorial, synthesize_brief_editorial
from prm.briefs import (
    BriefBuildRequest, BriefDocumentStore, BriefWindow, CoverageSource, build_brief_document,
    render_brief_document, _storage_document, _stored_document,
)
from prm.contracts import OperatorRequest
from prm.conversation import ConversationStore
from prm.routing import brief_topic_query
from tests.test_prm_synthesis import _archive_access


def _request():
    window = BriefWindow.from_iso(timezone_name="Europe/Berlin", start_at="2026-09-12T00:00:00+02:00",
                                 end_at="2026-09-19T00:00:00+02:00", generated_at="2026-09-19T01:00:00+02:00")
    texts = (
        "Orion SDK сохраняет результат завершённого шага. После перезапуска агент продолжает задачу с этого шага.",
        "Документация Orion SDK описывает сохранение результатов шагов. Восстановление работает для завершённых шагов.",
        "Личное поздравление автора канала и рекламная ссылка. Событий по теме в этом сообщении нет.",
    )
    evidence = tuple({
        "local_archive_provenance": True, "evidence_id": f"evidence_source_{i}",
        "source_url": f"https://example.org/source/{i}", "title": f"@channel_{i}",
        "support_span": text, "topics": ["AI"], "posted_at": "2026-09-15T10:00:00+02:00",
    } for i, text in enumerate(texts))
    return BriefBuildRequest(topic="AI", window=window, evidence=evidence)


def _editorial_data():
    evidence = _request().evidence
    return {"stories": [{
        "title": "Orion SDK продолжает задачу после перезапуска",
        "summary": "Агент сохраняет завершённые шаги и использует их при продолжении задачи.",
        "explanation": "Сохранённый результат позволяет продолжить задачу после перезапуска. Документация ограничивает восстановление завершёнными шагами.",
        "why_selected": "Это полезный механизм для устойчивости длительных исследований.",
        "next_step": "Если исследование прерывается, можно проверить восстановление на небольшой задаче.",
        "caveat": "Поведение незавершённого шага в этих фрагментах не описано.",
        "anchors": [{"evidence_ref": f"evidence_source_{i}", "quote": evidence[i]["support_span"]} for i in (0, 1)],
    }], "omitted_refs": ["evidence_source_2"]}


def _edited_document():
    request = _request()
    base = build_brief_document(request)
    return build_brief_document(replace(request, editorial=BriefEditorial.from_dict(_editorial_data(), base.evidence)))


@pytest.mark.parametrize("query,expected", [
    ("AI за последнюю неделю", "AI"),
    ("Собери полный бриф AI за прошлую неделю", "AI"),
    ("бриф AI с 2026-09-12 по 2026-09-19 timezone Europe/Berlin", "AI"),
    ("weekly brief agent evals last week", "agent evals"),
])
def test_brief_retrieval_separates_topic_from_time_and_presentation(query, expected):
    assert brief_topic_query(query) == expected


def test_event_groups_sources_without_priority_metadata_and_has_substantive_detail():
    document = _edited_document()
    assert all(item.importance == "unknown" for item in document.evidence)
    assert len(document.editorial.stories) == 1
    short = render_brief_document(document)
    full = render_brief_document(document, view="full")
    assert "Orion SDK продолжает задачу" in short
    assert "@channel" not in short + full
    assert "важности" not in short
    assert "срок не указан" not in full
    assert "Документация ограничивает" in full
    assert "Если исследование прерывается" in full
    assert "Личное поздравление" not in full
    assert "https://example.org/source/0" in full and "https://example.org/source/1" in full
    assert "это не полный" in full.casefold()
    assert len(short) < 2400
    schema = json.loads(Path("schemas/assistant_brief_document.v1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(document.to_dict())


@pytest.mark.parametrize("mutation", ["source", "quote", "number", "omission", "handle", "markup"])
def test_editorial_rejects_unbound_facts_and_unaccounted_sources(mutation):
    data = _editorial_data()
    story = data["stories"][0]
    if mutation == "source":
        story["anchors"][0]["evidence_ref"] = "evidence_not_selected"
    elif mutation == "quote":
        story["anchors"][0]["quote"] = "Invented claim that the source does not contain."
    elif mutation == "number":
        story["summary"] += " Производительность выросла в 99 раз."
    elif mutation == "omission":
        data["omitted_refs"] = []
    elif mutation == "handle":
        story["title"] = "@channel"
    else:
        story["summary"] = '<a href="https://evil.example/">Click</a>'
    with pytest.raises(ValueError):
        BriefEditorial.from_dict(data, build_brief_document(_request()).evidence)


def test_editorial_content_is_durable_and_part_of_report_identity():
    document = _edited_document()
    assert _stored_document(_storage_document(document)) == document
    altered = _storage_document(document)
    altered["editorial"]["stories"][0]["explanation"] = "Другая версия объяснения."
    with pytest.raises(ValueError, match="identity"):
        _stored_document(altered)
    plain = build_brief_document(_request())
    assert _stored_document(_storage_document(plain)) == plain
    assert plain.content_digest != document.content_digest
    assert plain.brief_id != document.brief_id


def test_editorial_followups_reuse_event_numbering_explanations_and_sources(monkeypatch):
    doc = _edited_document()
    request = replace(_request(), editorial=doc.editorial)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"),
        conversations=ConversationStore(), briefs=BriefDocumentStore())
    def forbidden(*args, **kwargs):
        raise AssertionError("saved story discussion must not call retrieval or a provider")
    monkeypatch.setattr("prm.application.answer_memory_research", forbidden)
    monkeypatch.setattr("prm.application.synthesize_brief_editorial", forbidden)
    assistant.answer(OperatorRequest(query="AI", mode="brief", chat_id="42", brief_request=request))
    for query, fragment in (("объясни 1", "Документация ограничивает"),
                            ("что попробовать?", "Если исследование прерывается"),
                            ("сделай короче", "Агент сохраняет завершённые шаги"),
                            ("только AI", "Orion SDK")):
        result = assistant.answer(OperatorRequest(query=query, chat_id="42"))
        assert fragment in result.text
        assert result.payload["telegram_parse_mode"] == "HTML"
        assert "BriefDocument" not in result.text
        assert "https://example.org/source/0" in result.text
        assert result.payload["brief_document"]["brief_id"] == doc.brief_id


def test_editorial_transport_keeps_paired_permission_and_active_application_path(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(_editorial_data() if len(calls) == 1 else {"verdict": "pass", "issues": []}, ensure_ascii=False))
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("PRM_OPENAI_CONTEXT_EGRESS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-pa04-key")
    monkeypatch.setattr("prm.archive_synthesis_transport._build_client",
                        lambda _key: SimpleNamespace(responses=SimpleNamespace(create=create)))
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"),
        conversations=ConversationStore(), briefs=BriefDocumentStore())
    result = assistant.answer(OperatorRequest(query="AI", mode="brief", chat_id="42",
        brief_request=_request(), archive_synthesis_access=_archive_access()))
    assert len(calls) == 2
    assert "group reports of the same event" in calls[0]["input"][0]["content"]
    assert result.payload["brief_editorial"]["status"] == "source_anchored_reviewed"
    assert result.payload["brief_editorial"]["semantic_verification"] == "model_review_passed"
    assert "Orion SDK продолжает" in result.text
    assert "editorial" in result.payload["brief_document"]


def test_no_grant_never_calls_transport_and_rejected_generation_preserves_sources(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("no authorization must mean no provider call")
    monkeypatch.setattr("prm.archive_synthesis_transport.complete_archive_synthesis", forbidden)
    document = build_brief_document(_request())
    editorial, measurement = synthesize_brief_editorial(document, question="AI", access=None)
    assert editorial is None and measurement["provider_egress_attempted"] is False
    full = render_brief_document(document, view="full")
    assert "Редакторский обзор пока не подготовлен" in full
    assert "результат завершённого шага" in full


def test_provider_failure_or_invalid_json_does_not_publish_editorial(monkeypatch):
    class Receipt:
        def public_measurement(self):
            return {"provider_egress_attempted": True}
    monkeypatch.setattr("prm.archive_synthesis_transport.complete_archive_synthesis",
                        lambda **kwargs: SimpleNamespace(text='{"stories":[],"stories":[]}', receipt=Receipt()))
    editorial, measurement = synthesize_brief_editorial(build_brief_document(_request()), question="AI", access=_archive_access())
    assert editorial is None and measurement["status"] == "editorial_rejected"


def test_content_review_rejection_preserves_raw_report_instead_of_publishing(monkeypatch):
    class Receipt:
        def public_measurement(self):
            return {"provider_egress_attempted": True}
    modes = []
    def complete(**kwargs):
        modes.append(kwargs["response_mode"])
        text = _editorial_data() if len(modes) == 1 else {"verdict": "fail", "issues": ["unsupported_relationship"]}
        return SimpleNamespace(text=json.dumps(text, ensure_ascii=False), receipt=Receipt())
    monkeypatch.setattr("prm.archive_synthesis_transport.complete_archive_synthesis", complete)
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"), briefs=BriefDocumentStore(),
        conversations=ConversationStore()).answer(OperatorRequest(query="AI", mode="brief", chat_id="42",
        brief_request=_request(), archive_synthesis_access=_archive_access()))
    assert modes == ["brief_editorial", "brief_review"]
    assert result.payload["brief_editorial"]["status"] == "content_review_failed"
    assert "editorial" not in result.payload["brief_document"]


def test_review_budget_is_reserved_before_generation_and_never_bypassed(monkeypatch):
    from prm.brief_editorial import _reserve_content_review
    access = _archive_access()
    competing = _reserve_content_review(access)
    assert competing is not None
    monkeypatch.setattr("prm.archive_synthesis_transport._build_client",
                        lambda *_: pytest.fail("insufficient review budget must stop before transport"))
    editorial, measurement = synthesize_brief_editorial(build_brief_document(_request()), question="AI", access=access)
    assert editorial is None
    assert measurement == {"status": "review_budget_or_authorization_required", "provider_egress_attempted": False}


def test_expired_or_revoked_permission_prevents_editorial_transport(monkeypatch):
    access = _archive_access()
    registry = access.query_authorization.reservation.registry
    registry.revoke_grant(access.context_authorization.grant_ref)
    monkeypatch.setattr("prm.archive_synthesis_transport._build_client", lambda *_: pytest.fail("revoked context egress"))
    editorial, measurement = synthesize_brief_editorial(build_brief_document(_request()), question="AI", access=access)
    assert editorial is None and measurement["provider_egress_attempted"] is False


def test_normal_brief_route_retrieves_then_synthesizes_and_reuses_result(monkeypatch):
    requests = []
    def retrieve(question, **kwargs):
        requests.append(kwargs)
        return {"archive_evidence": {"items": [dict(item, archive_document_id=item["evidence_id"])
                                                for item in _request().evidence]}}
    monkeypatch.setattr("prm.application.answer_memory_research", retrieve)
    calls = []
    class Receipt:
        def public_measurement(self):
            return {"provider_egress_attempted": True}
    def complete(**kwargs):
        calls.append(kwargs["response_mode"])
        data = _editorial_data() if len(calls) == 1 else {"verdict": "pass", "issues": []}
        return SimpleNamespace(text=json.dumps(data, ensure_ascii=False), receipt=Receipt())
    monkeypatch.setattr("prm.archive_synthesis_transport.complete_archive_synthesis", complete)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"),
        conversations=ConversationStore(), briefs=BriefDocumentStore())
    result = assistant.answer(OperatorRequest(
        query="бриф AI с 2026-09-12 по 2026-09-19 timezone Europe/Berlin", mode="brief", chat_id="42",
        archive_synthesis_access=_archive_access(),
    ))
    assert requests[0]["archive_query"] == "AI"
    assert requests[0]["budget"].max_archive_candidates == 32
    assert requests[0]["limit"] == 8
    assert result.payload["brief_editorial"]["status"] == "source_anchored_reviewed"
    assert "Orion SDK продолжает" in result.text
    followup = assistant.answer(OperatorRequest(query="объясни 1", chat_id="42"))
    assert "Документация ограничивает" in followup.text
    assert len(requests) == 1 and calls == ["brief_editorial", "brief_review"]


@pytest.mark.parametrize("complete", [False, True])
def test_noise_only_brief_is_valid_empty_editorial_with_honest_coverage(monkeypatch, complete):
    request = _request()
    request = replace(request, evidence=(request.evidence[2],),
                      coverage=(CoverageSource("synthetic_archive", "checked" if complete else "partial"),))
    candidate = {"stories": [], "omitted_refs": ["evidence_source_2"]}
    calls = []
    class Receipt:
        def public_measurement(self):
            return {"provider_egress_attempted": True}
    def generate(**kwargs):
        calls.append(kwargs["response_mode"])
        output = candidate if len(calls) == 1 else {"verdict": "pass", "issues": []}
        return SimpleNamespace(text=json.dumps(output), receipt=Receipt())
    monkeypatch.setattr("prm.archive_synthesis_transport.complete_archive_synthesis", generate)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"),
        conversations=ConversationStore(), briefs=BriefDocumentStore())
    result = assistant.answer(OperatorRequest(query="AI", mode="brief", chat_id="42",
        brief_request=request, archive_synthesis_access=_archive_access()))
    assert calls == ["brief_editorial", "brief_review"]
    assert result.payload["brief_document"]["editorial"] == candidate
    assert result.payload["brief_editorial"]["status"] == "source_anchored_reviewed"
    full = assistant.answer(OperatorRequest(query="Показать полный бриф", chat_id="42"))
    for text in (result.text, full.text):
        assert "Личное поздравление" not in text and "@channel" not in text
        assert "Редакторский обзор пока не подготовлен" not in text
        if complete:
            assert "В проверенной области важных изменений" in text
        else:
            assert "Это не вывод за весь период" in text
            assert "важных изменений по теме не найдено" not in text
    document = build_brief_document(replace(request, editorial=BriefEditorial.from_dict(candidate, build_brief_document(request).evidence)))
    assert _stored_document(_storage_document(document)) == document
    jsonschema.Draft202012Validator(json.loads(Path("schemas/assistant_brief_document.v1.schema.json").read_text())).validate(document.to_dict())
    with pytest.raises(ValueError):
        BriefEditorial.from_dict({"stories": [], "omitted_refs": []}, document.evidence)
