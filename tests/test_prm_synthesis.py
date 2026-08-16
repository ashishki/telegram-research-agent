from prm.synthesis import synthesize_answer


def test_synthesis_rejects_diagnostic_fallback_markers(monkeypatch):
    def complete(**_kwargs):
        return "The local research path found grounded evidence. Archive signal: raw fallback."

    monkeypatch.setenv("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "1")
    monkeypatch.setenv("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", "1")
    monkeypatch.setattr("prm.synthesis.LLMClient.complete", complete)

    result = synthesize_answer(
        {
            "answer_gate": {"external_verification_required": False},
            "claim_ledger": {
                "claims": [
                    {
                        "claim_text": "Есть подтверждённый локальный сигнал.",
                        "evidence_refs": ["https://t.me/example/1"],
                        "support_status": "supported",
                    }
                ]
            },
            "project_fit": {},
        },
        deterministic_fallback="Короткий вывод\nЕсть подтверждённый локальный сигнал.",
        mode="research",
        evidence_items=[
            {
                "evidence_id": "e1",
                "support_span": "Есть подтверждённый локальный сигнал.",
                "source_url": "https://t.me/example/1",
            }
        ],
    )

    assert result is None
