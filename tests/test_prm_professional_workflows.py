from assistant.professional_workflows import (
    build_ai_systems_project_application_workflow,
    build_career_portfolio_gap_workflow,
    build_enterprise_ai_adoption_workflow,
    build_learning_experiment_workflow,
    build_writer_editor_brief_workflow,
    build_professional_answer,
)


def _payload(*, label: str = "direct_implication", current: bool = False) -> dict:
    return {
        "archive_evidence": {
            "items": [
                {
                    "snippet": "Agent runtime failed because an eval regression and retrieval citation guard were absent.",
                    "source_url": "https://t.me/example/1",
                }
            ]
        },
        "project_fit": {"relevance_label": label, "guidance": "Добавить проверку в active project."},
        "answer_gate": {"external_verification_required": current},
    }


def test_ai_systems_project_application_workflow():
    result = build_ai_systems_project_application_workflow(_payload())

    assert "eval_gap" in result["failure_taxonomy"]
    assert "retrieval_gap" in result["failure_taxonomy"]
    assert result["cited_cases"] == [{"source_url": "https://t.me/example/1", "snippet": "Agent runtime failed because an eval regression and retrieval citation guard were absent."}]
    assert result["project_implication"]
    assert result["project_action"]
    assert result["eval_case"]
    assert result["write_performed"] is False


def test_professional_answer_claims_have_citations_and_one_workflow():
    answer = build_professional_answer({**_payload(), "direct_answer": "Grounded result."}, workflow="ai_systems")
    assert answer["primary_workflow"] == "ai_systems"
    assert answer["key_findings"][0]["citation"] == "https://t.me/example/1"


def test_professional_answer_current_fact_has_no_action():
    answer = build_professional_answer({**_payload(current=True), "direct_answer": "Current claim."}, workflow="archive_research")
    assert answer["answer_status"] == "verification_required"
    assert answer["recommended_action"] is None


def test_ai_systems_no_keyword_only_action():
    result = build_ai_systems_project_application_workflow(_payload(label="weak_watch"))

    assert result["project_action"] is None
    assert result["eval_case"] is None


def test_ai_systems_freshness_boundary():
    result = build_ai_systems_project_application_workflow(_payload(current=True))

    assert result["external_verification_required"] is True
    assert result["answer_first_boundary"].startswith("Внешняя проверка нужна")
    assert result["project_action"] is None


def test_writer_editor_brief_workflow():
    result = build_writer_editor_brief_workflow(
        {
            **_payload(),
            "direct_answer": "AI adoption needs an explicit evaluation loop.",
            "next_steps": ["Сверить тезис с первоисточниками."],
        }
    )

    assert result["thesis"] == "AI adoption needs an explicit evaluation loop."
    assert result["cases"] == [
        {
            "claim": "Agent runtime failed because an eval regression and retrieval citation guard were absent.",
            "source_url": "https://t.me/example/1",
        }
    ]
    assert result["counterargument"]
    assert result["practical_conclusion"]
    assert result["sources"] == [{"source_url": "https://t.me/example/1"}]
    assert result["claims_requiring_external_verification"] == []
    assert result["ready_for_final_post"] is False


def test_editor_brief_marks_unverified_current_claims():
    result = build_writer_editor_brief_workflow({**_payload(current=True), "direct_answer": "Current market claim."})

    assert result["claims_requiring_external_verification"]
    assert "не финальный пост" in result["practical_conclusion"]
    assert result["ready_for_final_post"] is False


def test_enterprise_ai_adoption_workflow():
    result = build_enterprise_ai_adoption_workflow(
        {
            "archive_evidence": {
                "items": [
                    {
                        "snippet": "The product owner uses a manual workflow workaround for enterprise AI adoption.",
                        "source_url": "https://t.me/example/enterprise",
                    }
                ]
            },
            "project_fit": {
                "relevance_label": "direct_implication",
                "project_name": "Research Memory",
                "guidance": "Проверить гипотезу в active project.",
            },
        }
    )

    assert result["pain_pattern"]
    assert result["evidence_maturity"] == "telegram_discovery_only"
    assert result["buyer_owner_signal"]
    assert result["relevant_project"] == "Research Memory"
    assert result["validation_step"]
    assert result["do_not_build_boundary"]
    assert result["project_action"]


def test_telegram_only_product_claim_boundary():
    result = build_enterprise_ai_adoption_workflow(_payload())

    assert result["evidence_maturity"] == "telegram_discovery_only"
    assert "Не начинать реализацию" in result["do_not_build_boundary"]


def test_enterprise_no_project_action_without_direct_evidence():
    result = build_enterprise_ai_adoption_workflow(_payload(label="weak_watch"))

    assert result["guidance"] == "watch_or_reference"
    assert result["project_action"] is None


def test_learning_experiment_workflow():
    result = build_learning_experiment_workflow({**_payload(), "concept": "контекст-инжиниринг"})

    assert result["plain_explanation"]
    assert result["analogy"]
    assert result["source_evidence"] == [
        {
            "source_url": "https://t.me/example/1",
            "snippet": "Agent runtime failed because an eval regression and retrieval citation guard were absent.",
        }
    ]
    assert result["existing_knowledge_relation"]
    assert result["experiment_proposal"]
    assert result["success_criterion"]
    assert result["reflection_question"]
    assert result["learning_state"] == "unknown"


def test_learning_experiment_confirmation_boundary():
    result = build_learning_experiment_workflow(_payload())

    assert result["persistence"] == {"requires_confirmation": True, "write_performed": False}


def test_career_portfolio_gap_workflow():
    result = build_career_portfolio_gap_workflow(_payload())

    assert result["recurring_requirement"]
    assert result["source_evidence"]
    assert result["current_portfolio_evidence"]
    assert result["missing_proof"] is None
    assert result["next_portfolio_action"]


def test_missing_portfolio_repo_not_fabricated():
    result = build_career_portfolio_gap_workflow(_payload(label="weak_watch"))

    assert result["current_portfolio_evidence"] == "unknown"
    assert result["missing_proof"]
    assert result["next_portfolio_action"] is None


def test_career_current_market_verification_boundary():
    result = build_career_portfolio_gap_workflow(_payload(current=True))

    assert result["external_verification_required"] is True
    assert result["market_boundary"]
    assert result["next_portfolio_action"] is None
