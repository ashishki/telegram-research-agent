import pytest

from assistant.prm_refresh_receipt import build_refresh_receipt, render_refresh_receipt


def test_independent_statuses():
    receipt = build_refresh_receipt(
        {
            "archive": {"status": "ok", "count": 4},
            "reactions": {"status": "failed", "reason": "credentials unavailable"},
            "vector": {"status": "stale"},
            "enrichment": {"status": "not_run"},
        }
    )

    rendered = render_refresh_receipt(receipt)

    assert "Архив: готово" in rendered
    assert "Реакции: ошибка — component_failed" in rendered
    assert "Векторный индекс: устарело" in rendered
    assert receipt["write_performed"] is False
    assert receipt["schedule_changed"] is False


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        build_refresh_receipt({"archive": {"status": "running"}})


def test_reason_text_is_reduced_to_safe_code():
    receipt = build_refresh_receipt({"archive": {"status": "failed", "reason": "token=secret /srv/private"}})

    assert receipt["components"]["archive"]["reason"] == "component_failed"
    assert "secret" not in render_refresh_receipt(receipt)
