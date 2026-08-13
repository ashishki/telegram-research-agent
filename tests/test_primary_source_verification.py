from assistant.primary_source_verification import (
    build_primary_source_verification_plan,
    render_primary_source_verification_answer,
)


def test_verification_requires_approval_before_live_fetch():
    result = build_primary_source_verification_plan(
        {"telegram_source_refs": ["https://t.me/example/1"], "candidate_source_urls": ["https://docs.example.com/api"]}
    )

    assert result["status"] == "verification_required_not_run"
    assert result["live_fetch"] == {
        "performed": False,
        "approval_required": True,
        "trust_record_required": True,
        "approved": False,
    }
    assert result["write_performed"] is False


def test_direct_primary_source_preference():
    result = build_primary_source_verification_plan(
        {
            "candidate_source_urls": [
                "https://search.example.net/result",
                "https://github.com/openai/example",
                "https://docs.example.com/reference",
            ]
        }
    )

    assert [item["source_url"] for item in result["primary_source_plan"]] == [
        "https://docs.example.com/reference",
        "https://github.com/openai/example",
        "https://search.example.net/result",
    ]


def test_verification_answer_contract():
    answer = render_primary_source_verification_answer(
        {"telegram_source_refs": ["https://t.me/example/1"], "candidate_source_urls": ["https://github.com/openai/example"]}
    )

    for label in (
        "Telegram-сигнал:",
        "Первоисточник:",
        "Независимое подтверждение:",
        "Изменившиеся факты:",
        "Неизвестно:",
        "Пересмотренная рекомендация:",
    ):
        assert label in answer
