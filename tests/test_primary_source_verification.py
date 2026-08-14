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
                {"url": "https://docs.example.com/reference", "official_relation": True},
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


def test_network_boundaries_reject_private_ip_and_http():
    result = build_primary_source_verification_plan(
        {"candidate_source_urls": ["http://docs.example.com/insecure", "https://127.0.0.1/private", {"url": "https://docs.example.com/safe", "official_relation": True}]}
    )

    assert result["primary_source_plan"] == [{"source_url": "https://docs.example.com/safe", "evidence_class": "official_or_github"}]


def test_official_relation_required():
    result = build_primary_source_verification_plan(
        {"candidate_source_urls": ["https://www.example.com/announcement", {"url": "https://vendor.example.com/news", "official_relation": True}]}
    )

    classes = {item["source_url"]: item["evidence_class"] for item in result["primary_source_plan"]}
    assert classes["https://vendor.example.com/news"] == "official_or_github"
    assert classes["https://www.example.com/announcement"] == "other"


def test_lookalike_github_and_docs_hosts_are_not_official():
    result = build_primary_source_verification_plan(
        {"candidate_source_urls": ["https://notgithub.com/openai", "https://docs-evil.example/guide"]}
    )

    assert all(item["evidence_class"] == "other" for item in result["primary_source_plan"])
