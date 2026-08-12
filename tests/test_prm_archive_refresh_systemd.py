from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prm_archive_refresh_service_uses_bounded_safe_command():
    service = (ROOT / "systemd" / "telegram-prm-archive-refresh.service").read_text()

    assert "Type=oneshot" in service
    assert (
        "ExecStart=/srv/openclaw-you/venv/bin/python3 src/main.py memory refresh-archive "
        "--days 21 --confirm-canonical-write --json"
    ) in service
    assert "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=0" in service
    assert "PRM_TELEGRAM_AUTO_LLM_ROUTER=0" in service
    assert "PRM_TELEGRAM_RAG_LLM_SYNTHESIS=0" in service
    assert "src/main.py ingest" not in service
    assert "weekly-intelligence" not in service
    assert "mvp-weekly" not in service
    assert " bot" not in service


def test_prm_archive_refresh_timer_runs_weekly_without_install_time_catchup():
    timer = (ROOT / "systemd" / "telegram-prm-archive-refresh.timer").read_text()

    assert "OnCalendar=Mon *-*-* 08:10:00 Europe/Berlin" in timer
    assert "Persistent=false" in timer
    assert "Unit=telegram-prm-archive-refresh.service" in timer
    assert "Requires=telegram-prm-archive-refresh.service" not in timer
