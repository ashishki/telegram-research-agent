from types import SimpleNamespace

from prm.application import PersonalResearchAssistant
from prm.contracts import AssistantResult, OperatorRequest


def _payload():
    return {
        "status": "ok",
        "direct_answer": "В архиве есть подтверждённый сигнал.",
        "answer_gate": {"allow_answer": True, "external_verification_required": False, "current_claim_allowed": True},
        "archive_evidence": {"items": [{
            "archive_document_id": "tg:1", "snippet": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "channel_username": "example", "posted_at": "2026-08-01",
            "matched_query_variant": "agent evals",
        }]},
        "evidence_quality": {"items": [{
            "evidence_id": "e1", "support_span": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "source_group_id": "g1", "freshness_status": "fresh",
            "relevance_label": "direct",
        }]},
        "professional_answer": {"short_answer": "В архиве есть подтверждённый сигнал.", "key_findings": [],
                                "recommended_action": None, "uncertainty": [], "workflow_section": {},
                                "answer_status": "supported", "professional_lens": "neutral",
                                "primary_workflow": "archive_research"},
        "project_fit": {}, "project_decision": {}, "claim_ledger": {"claims": []},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }


def test_application_returns_intent_specific_archive_contract(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(
        query="Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?",
        mode="auto",
    ))
    assert isinstance(result, AssistantResult)
    assert result.mode == "research"
    assert result.route["primary_intent"] == "archive_to_action"
    assert result.route["project_context_required"] is False
    assert result.payload["response_contract_id"] == "archive_research.v2"
    assert result.text.startswith("В архиве найдено 1 прямых")
    assert "Главный риск" not in result.text


def test_archive_to_action_uses_bounded_research_plan(monkeypatch):
    payload = _payload()
    payload["archive_candidate_pool"] = [
        {**payload["archive_evidence"]["items"][0], "source_role": "practical_evidence", "supports_action": True,
         "retrieval_mode": "hybrid_fts_vector"},
        {"archive_document_id": "promo", "snippet": "Agent evals webinar registration", "source_url": "https://t.me/example/2", "source_role": "announcement_or_promotion", "supports_action": False},
    ]
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    monkeypatch.setattr("prm.application.plan_archive_evidence", lambda *args, **kwargs: {
        "selected_evidence_ids": ["tg:1"], "candidate_count": 2, "selected_count": 1,
        "selection_mode": "deterministic_role_rank", "provider_egress": False,
        "items": [payload["archive_candidate_pool"][0]],
    })

    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(OperatorRequest(
        query="Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?",
        mode="auto",
    ))

    assert result.payload["research_plan"]["candidate_count"] == 2
    assert result.payload["archive_evidence"]["items"][0]["archive_document_id"] == "tg:1"
    assert result.payload["archive_evidence"]["items"][0]["retrieval_mode"] == "hybrid_fts_vector"
    assert result.payload["research_plan"]["gap_check"] == {}


def test_ambiguous_project_clarifies(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("retrieval must not run")

    monkeypatch.setattr("prm.application.answer_memory_research", fail)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(query="Стоит ли добавить это в backlog моего проекта?"))
    assert result.mode == "project_clarify"
    assert "К какому проекту" in result.text
    assert called is False


def test_free_text_memory_action_does_not_run_archive_search_or_write(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("free-text memory action must not run archive search")

    monkeypatch.setattr("prm.application.answer_memory_research", fail)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(
        OperatorRequest(query="сохрани заметку, но сначала покажи что именно сохранишь")
    )

    assert result.status == "needs_confirmation"
    assert result.route["primary_intent"] == "memory_action"
    assert result.payload["write_performed"] is False
    assert result.payload["answer_gate"]["allow_answer"] is False
    assert "не делаю durable-запись" in result.text
    assert "Сохранить" in result.text
    assert called is False
