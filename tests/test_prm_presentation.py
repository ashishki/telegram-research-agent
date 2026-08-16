from prm.presentation import render_payload


def test_project_decision_rendering_is_user_facing_russian():
    text = render_payload(
        {
            "project_fit": {
                "project_name": "gdev-agent",
                "relevance_label": "direct_implication",
                "guidance": "Можно применить к проекту только через маленькое проверяемое действие.",
            },
            "project_decision": {
                "grounded_recommendation": "Для gdev-agent: сделать одну проверку по agent operations.",
                "project_goal": "support triage, guardrails, human approval, evaluation",
                "current_blocker": "Главный риск - слишком широкий action.",
                "acceptance_criterion": "Есть проверка с агентом, уровнем доступа и местом аудита.",
                "next_proof": "Проверить один источник на проекте.",
            },
            "claim_ledger": {
                "claims": [
                    {
                        "claim_text": "Agent Operations требует контроля доступа и аудита.",
                    }
                ]
            },
            "unknowns": ["approved linked-source text", "live external freshness"],
            "archive_evidence": {
                "items": [
                    {
                        "posted_at": "2026-05-13T10:00:00Z",
                        "channel_username": "@leadgr",
                        "source_url": "https://t.me/leadgr/2367",
                    }
                ]
            },
        },
        mode="research",
    )

    assert "разбор обращений, защитные ограничения" in text
    assert "@@leadgr" not in text
    assert "approved linked-source text" not in text
    assert "live external freshness" not in text
    assert "Acceptance:" not in text
    assert "PR-sized" not in text
