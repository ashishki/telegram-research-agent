from assistant.prm_status import build_prm_status

def test_safe_status():
    result = build_prm_status({"health":{"status":"ok"}, "freshness":{"status":"stale"}, "reactions":{"status":"unavailable"}, "vector":{"status":"ok"}, "budget":{"status":"unknown"}, "token":"secret"})
    assert result["freshness"]["status"] == "stale"
    assert result["secrets_exposed"] is False
    assert result["write_performed"] is False
