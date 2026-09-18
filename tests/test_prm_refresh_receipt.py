import pytest
import sqlite3

from assistant.prm_refresh_receipt import build_archive_health_receipt, build_refresh_receipt, render_refresh_receipt


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


def test_archive_health_reads_coverage_without_starting_refresh(tmp_path):
    db_path = tmp_path / "archive.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE posts (posted_at TEXT)")
        connection.execute("INSERT INTO posts(posted_at) VALUES ('2026-09-15T11:00:00Z')")

    receipt = build_archive_health_receipt(db_path)
    rendered = render_refresh_receipt(receipt)

    assert receipt["write_performed"] is False
    assert receipt["archive_health"]["coverage_at"] == "2026-09-15T11:00:00Z"
    assert receipt["archive_health"]["last_attempt"] == "unknown"
    assert "Покрытие архива до: 2026-09-15T11:00:00Z" in rendered
    assert "Ничего не запускалось" in rendered


def test_archive_health_distinguishes_missing_source_from_empty_archive(tmp_path):
    missing = build_archive_health_receipt(tmp_path / "absent.db")
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE posts (posted_at TEXT)")
    empty = build_archive_health_receipt(db_path)

    assert missing["components"]["archive"]["status"] == "failed"
    assert empty["components"]["archive"]["status"] == "stale"
