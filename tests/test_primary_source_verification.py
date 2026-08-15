from assistant.primary_source_verification import (
    classify_trusted_source,
    execute_primary_source_verification,
)


def test_primary_source_classification_requires_explicit_official_relation():
    assert classify_trusted_source("https://github.com/owner/repo")["evidence_class"] == "github_repository"
    assert classify_trusted_source("https://arxiv.org/abs/2401.00001")["evidence_class"] == "research_paper"
    assert classify_trusted_source("https://www.vendor.example/docs")["evidence_class"] == "unknown"
    assert (
        classify_trusted_source("https://docs.vendor.example/guide", official_relation=True)["evidence_class"]
        == "official_documentation"
    )
    assert classify_trusted_source("https://127.0.0.1/admin")["safety_status"] == "private_address"


def test_execute_primary_source_verification_uses_fake_transport_and_cache(tmp_path):
    calls = []

    def transport(url: str) -> dict:
        calls.append(url)
        return {
            "status": 200,
            "headers": {"content-type": "text/html; charset=utf-8"},
            "body": b"<html><title>README</title>license tests github actions</html>",
            "final_url": url,
        }

    payload = {
        "approvals": {"live_fetch_approved": True, "trust_record_approved": True},
        "telegram_source_refs": ["https://t.me/example/1"],
        "candidate_source_urls": [{"source_url": "https://github.com/owner/repo", "official_relation": True}],
    }

    first = execute_primary_source_verification(payload, transport=transport, cache_dir=tmp_path)
    second = execute_primary_source_verification(payload, transport=transport, cache_dir=tmp_path)

    assert first["status"] == "verification_fetched"
    assert first["fetch_results"][0]["evidence_class"] == "github_repository"
    assert first["fetch_results"][0]["github_repository"]["repository"] == "owner/repo"
    assert second["fetch_results"][0]["cache_hit"] is True
    assert calls == ["https://github.com/owner/repo"]


def test_verification_does_not_fetch_without_approval(tmp_path):
    result = execute_primary_source_verification(
        {"candidate_source_urls": ["https://github.com/owner/repo"], "approvals": {}},
        transport=lambda _url: {"status": 200, "headers": {}, "body": b""},
        cache_dir=tmp_path,
    )

    assert result["status"] == "verification_required_not_run"
    assert result["fetch_results"] == []
