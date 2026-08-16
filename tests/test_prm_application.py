from types import SimpleNamespace

from prm.application import PersonalResearchAssistant
from prm.contracts import AssistantResult, OperatorRequest


def _payload():
    return {
        "status": "ok",
        "direct_answer": "В архиве есть подтверждённый сигнал.",
        "answer_gate": {"allow_answer": True, "external_verification_required": False, "current_claim_allowed": True},
        "archive_evidence": {"items": [{"snippet": "Подтверждённый сигнал про eval gates.", "source_url": "https://t.me/example/1", "channel_username": "example", "posted_at": "2026-08-01"}]},
        "evidence_quality": {"items": [{"evidence_id": "e1", "support_span": "Подтверждённый сигнал про eval gates.", "source_url": "https://t.me/example/1", "source_group_id": "g1", "freshness_status": "fresh"}]},
        "professional_answer": {"short_answer": "В архиве есть подтверждённый сигнал.", "key_findings": [{"claim": "Подтверждённый сигнал про eval gates.", "citation": "https://t.me/example/1"}], "recommended_action": None, "uncertainty": [], "workflow_section": {}, "answer_status": "supported", "professional_lens": "neutral", "primary_workflow": "archive_research"},
        "project_fit": {},
        "claim_ledger": {"claims": []},
        "unknowns": [],
        "next_steps": {},
        "receipt": {},
        "privacy": {},
    }


def test_application_returns_one_response_contract(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(query="Что есть про eval gates?", mode="research"))
    assert isinstance(result, AssistantResult)
    assert result.mode == "research"
    assert "Короткий вывод" in result.text
    assert result.operator_context["primary_workflow"] == "archive_research"


def test_ambiguous_project_clarifies(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("retrieval must not run")

    monkeypatch.setattr("prm.application.answer_memory_research", fail)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(query="Что применить к моему проекту?"))
    assert result.mode == "project_clarify"
    assert "К какому проекту" in result.text
    assert called is False
