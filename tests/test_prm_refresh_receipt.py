from assistant.prm_refresh_receipt import build_operator_refresh_receipt, build_refresh_failure_receipt


def test_operator_refresh_receipt_contract():
    receipt = build_operator_refresh_receipt(
        {
            "status": "ok",
            "before": {"posts": 10},
            "after": {"posts": 14, "max_posted_at": "2026-08-12T08:00:00Z"},
            "channels_touched": 3,
            "privacy": {
                "provider_egress": False,
                "migrations_run": False,
                "reaction_sync": False,
                "local_vector_sidecar_write": False,
                "dogfood_evidence": False,
                "release_claim": False,
            },
        }
    )

    assert receipt["new_posts"] == 4
    assert receipt["channels_touched"] == 3
    assert receipt["latest_posted_at"] == "2026-08-12T08:00:00Z"
    assert receipt["reaction_summary"]["status"] == "not_run"
    assert receipt["enrichment"]["status"] == "not_run"
    assert receipt["boundaries"]["report_generation"] is False
    assert receipt["boundaries"]["provider_egress"] is False
    assert "raw_posts" not in receipt


def test_refresh_failure_boundary():
    receipt = build_refresh_failure_receipt()

    assert receipt["status"] == "failed"
    assert receipt["new_posts"] == 0
    assert all(value is False for value in receipt["boundaries"].values())
