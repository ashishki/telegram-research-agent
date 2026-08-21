from prm.research_planner import assess_research_gaps, plan_archive_evidence


QUESTION = "Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?"


def test_gap_check_requests_local_practice_search_for_context_only_agent_evals():
    gap = assess_research_gaps([
        {
            "archive_document_id": "promo",
            "relevance_label": "partial",
            "source_role": "announcement_or_promotion",
            "supports_action": False,
        }
    ], question=QUESTION)

    assert gap["status"] == "needs_gap_search"
    assert "replayable_practice" in gap["missing_evidence"]
    assert "agent evals harness regression fixture" in gap["query_variants"]


def test_fallback_research_plan_prefers_practical_evidence_without_provider_egress(monkeypatch):
    monkeypatch.delenv("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", raising=False)
    plan = plan_archive_evidence([
        {"archive_document_id": "context", "relevance_label": "partial", "supports_action": False},
        {"archive_document_id": "practice", "relevance_label": "direct", "supports_action": True},
    ], question=QUESTION)

    assert plan["selection_mode"] == "deterministic_role_rank"
    assert plan["provider_egress"] is False
    assert plan["selected_evidence_ids"][0] == "practice"


def test_gap_check_stops_after_practical_evidence_is_present():
    gap = assess_research_gaps([
        {
            "archive_document_id": "practice",
            "relevance_label": "direct",
            "source_role": "practical_evidence",
            "supports_action": True,
        }
    ], question=QUESTION)

    assert gap["status"] == "sufficient"
    assert gap["query_variants"] == []
