from assistant.primary_source_verification import (
    build_primary_source_claim_ledger,
    classify_trusted_source,
    execute_primary_source_verification,
)


def test_direct_fixture_record_cannot_bypass_primary_source_claim_boundary():
    result = build_primary_source_claim_ledger(
        {"telegram_claim": "synthetic claim"},
        [{"status": "fetched", "fixture_origin": False, "primary_source_attested": True, "source_url": "https://github.com/x/y", "text_excerpt": "synthetic claim"}],
    )
    assert result["claim_ledger"]["claim_count"] == 1
    assert result["claim_ledger"]["claims"][0]["support_status"] == "unsupported"


def test_primary_source_classification_requires_explicit_official_relation():
    assert classify_trusted_source("https://github.com/owner/repo")["evidence_class"] == "github_repository"
    assert classify_trusted_source("https://arxiv.org/abs/2401.00001")["evidence_class"] == "research_paper"
    assert classify_trusted_source("https://www.vendor.example/docs")["evidence_class"] == "unknown"
    assert (
        classify_trusted_source("https://docs.vendor.example/guide", official_relation=True)["evidence_class"]
        == "official_documentation"
    )
    assert classify_trusted_source("https://127.0.0.1/admin")["safety_status"] == "ip_literal"
    result = execute_primary_source_verification(
        {
            "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["127.0.0.1", "éxample.com"]},
            "candidate_source_urls": ["https://example.com/"],
        },
        fixture_responses={},
    )
    assert result["fetch_results"][0]["status"] == "untrusted_candidate"


def test_execute_primary_source_verification_uses_fixture_responses_and_cache(tmp_path):
    fixtures = {
        "https://github.com/owner/repo": {
            "status": 200,
            "headers": {"content-type": "text/html"},
            "body": b"<html><title>README</title>license tests github actions</html>",
            "final_url": "https://github.com/owner/repo",
        }
    }

    payload = {
        "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["github.com"]},
        "telegram_source_refs": ["https://t.me/example/1"],
        "candidate_source_urls": [{"source_url": "https://github.com/owner/repo", "official_relation": True}],
    }

    first = execute_primary_source_verification(payload, fixture_responses=fixtures, cache_dir=tmp_path)
    second = execute_primary_source_verification(payload, fixture_responses=fixtures, cache_dir=tmp_path)

    assert first["status"] == "verification_required_not_run"
    assert first["fetch_results"][0]["status"] == "fixture_checked_not_verified"
    assert first["fetch_results"][0]["evidence_class"] == "github_repository"
    assert first["fetch_results"][0]["text_excerpt"]
    assert first["fetch_results"][0]["github_repository"]["repository"] == "owner/repo"
    assert second["fetch_results"][0]["cache_hit"] is True
    assert second["fetch_results"][0]["status"] == "cached_fixture"


def test_verification_does_not_fetch_without_approval(tmp_path):
    result = execute_primary_source_verification(
        {"candidate_source_urls": ["https://github.com/owner/repo"], "approvals": {}},
        fixture_responses={},
        cache_dir=tmp_path,
    )

    assert result["status"] == "verification_required_not_run"
    assert result["fetch_results"] == []


def test_verification_never_uses_live_network_even_when_legacy_flag_is_true():
    result = execute_primary_source_verification(
        {
            "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["github.com"]},
            "candidate_source_urls": ["https://github.com/owner/repo"],
        },
        allow_live_fetch=True,
    )

    assert result["status"] == "verification_required_not_run"
    assert result["fetch_results"] == []


def test_fixture_response_rejects_untrusted_candidate_and_cross_host_redirect(tmp_path):
    result = execute_primary_source_verification(
        {
            "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["docs.vendor.example"]},
            "candidate_source_urls": ["https://untrusted.example/x", "https://docs.vendor.example/changelog"],
        },
        fixture_responses={"https://docs.vendor.example/changelog": {"status": 200, "headers": {"content-type": "text/plain"}, "body": b"verified", "final_url": "https://elsewhere.example/result"}},
        cache_dir=tmp_path,
    )

    assert result["fetch_results"][0]["status"] == "rejected_redirect"
    assert result["fetch_results"][1]["status"] == "untrusted_candidate"


def test_malformed_trusted_hosts_and_cross_host_cache_cannot_become_evidence(tmp_path):
    payload = {
        "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": "github.com"},
        "candidate_source_urls": ["https://g/"],
    }
    result = execute_primary_source_verification(payload, fixture_responses={})
    assert result["fetch_results"] == []

    trusted_payload = {
        "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["docs.vendor.example"]},
        "candidate_source_urls": ["https://docs.vendor.example/changelog"],
    }
    cache_file = tmp_path / "70695148fc0f5a3b922d7beb6acfdc5e1273b894ebd1b65de89b722e34c364d6.json"
    cache_file.write_text('{"status":"fetched","source_url":"https://docs.vendor.example/changelog","final_url":"https://elsewhere.example/","fetched_at":"2099-01-01T00:00:00Z"}', encoding="utf-8")
    result = execute_primary_source_verification(
        trusted_payload,
        fixture_responses={"https://docs.vendor.example/changelog": {"status": 200, "headers": {"content-type": "text/plain"}, "body": b"ok", "final_url": "https://docs.vendor.example/changelog"}},
        cache_dir=tmp_path,
    )
    assert result["status"] == "verification_required_not_run"


def test_cache_only_does_not_claim_verification_or_update_claims(tmp_path):
    payload = {
        "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["github.com"]},
        "telegram_claim": "a claim",
        "candidate_source_urls": ["https://github.com/owner/repo"],
    }
    fixtures = {"https://github.com/owner/repo": {"status": 200, "headers": {"content-type": "text/plain"}, "body": b"a claim", "final_url": "https://github.com/owner/repo"}}
    execute_primary_source_verification(payload, fixture_responses=fixtures, cache_dir=tmp_path)
    cached = execute_primary_source_verification(payload, fixture_responses=fixtures, cache_dir=tmp_path)

    assert cached["status"] == "verification_required_not_run"
    assert cached["claim_ledger"]["claim_count"] == 0


def test_primary_source_fixture_result_never_enters_claim_ledger(tmp_path):
    fixtures = {
        "https://docs.vendor.example/changelog": {
            "status": 200,
            "headers": {"content-type": "text/plain"},
            "body": b"The official changelog confirms claim ledger verification before synthesis.",
            "final_url": "https://docs.vendor.example/changelog",
        }
    }

    result = execute_primary_source_verification(
        {
            "approvals": {"live_fetch_approved": True, "trust_record_approved": True, "trusted_hosts": ["docs.vendor.example"]},
            "telegram_source_refs": ["https://t.me/example/2"],
            "telegram_claim": "claim ledger verification before synthesis",
            "candidate_source_urls": [{"source_url": "https://docs.vendor.example/changelog", "official_relation": True}],
        },
        fixture_responses=fixtures,
        cache_dir=tmp_path,
    )

    assert result["status"] == "verification_required_not_run"
    assert result["claim_ledger"]["claim_count"] == 0
    assert "official source" not in result["revised_recommendation"]
