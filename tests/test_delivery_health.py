import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from output.delivery_health import build_weekly_delivery_health, format_weekly_delivery_health


def _active_timer_runner(*_args, **_kwargs):
    return subprocess.CompletedProcess(["systemctl"], 0, stdout="active\n", stderr="")


def _inactive_timer_runner(*_args, **_kwargs):
    return subprocess.CompletedProcess(["systemctl"], 3, stdout="inactive\n", stderr="")


def _systemd_unavailable_runner(*_args, **_kwargs):
    return subprocess.CompletedProcess(
        ["systemctl"],
        1,
        stdout="",
        stderr="System has not been booted with systemd as init system",
    )


def _write_split_outputs(root: Path, week_label: str = "2026-W28") -> tuple[Path, Path]:
    weekly_dir = root / "data" / "output" / "weekly_intelligence_briefs"
    atlas_dir = root / "data" / "output" / "knowledge_atlas"
    weekly_dir.mkdir(parents=True)
    atlas_dir.mkdir(parents=True)
    weekly_path = weekly_dir / f"{week_label}.weekly-brief.html"
    atlas_path = atlas_dir / f"{week_label}.knowledge-atlas.html"
    weekly_path.write_text("<html>brief</html>", encoding="utf-8")
    atlas_path.write_text("<html>atlas</html>", encoding="utf-8")
    return weekly_path, atlas_path


class TestWeeklyDeliveryHealth(unittest.TestCase):
    def test_missing_current_week_split_reports_after_scheduled_window_is_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            health = build_weekly_delivery_health(
                project_root=Path(tmpdir),
                now=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
                timer_runner=_active_timer_runner,
            )

        rendered = "\n".join(format_weekly_delivery_health(health, relative_to=Path(tmpdir)))
        self.assertIn("current_week_split_report_missing", health.failure_reasons)
        self.assertIn("WARNING: current-week split HTML reports missing after scheduled window week=2026-W28", rendered)

    def test_missing_current_week_split_reports_before_scheduled_window_is_not_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            health = build_weekly_delivery_health(
                project_root=Path(tmpdir),
                now=datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc),
                timer_runner=_active_timer_runner,
            )

        self.assertFalse(health.report_due)
        self.assertNotIn("current_week_split_report_missing", health.failure_reasons)

    def test_inactive_weekly_report_timer_is_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_split_outputs(root)
            health = build_weekly_delivery_health(
                project_root=root,
                now=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
                timer_runner=_inactive_timer_runner,
            )

        rendered = "\n".join(format_weekly_delivery_health(health, relative_to=Path(tmpdir)))
        self.assertIn("weekly_report_timer_inactive", health.failure_reasons)
        self.assertIn("weekly_delivery_timer: timer=telegram-ai-split-report.timer state=inactive checked=yes", rendered)
        self.assertIn("WARNING: telegram-ai-split-report.timer is inactive", rendered)

    def test_systemd_unavailable_is_reported_without_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_split_outputs(root)
            health = build_weekly_delivery_health(
                project_root=root,
                now=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
                timer_runner=_systemd_unavailable_runner,
            )

        rendered = "\n".join(format_weekly_delivery_health(health, relative_to=Path(tmpdir)))
        self.assertNotIn("weekly_report_timer_inactive", health.failure_reasons)
        self.assertIn("weekly_delivery_timer: timer=telegram-ai-split-report.timer state=unavailable checked=no", rendered)

    def test_root_owned_output_files_are_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            owned_file, _atlas_file = _write_split_outputs(root)

            def fake_uid(path: Path) -> int:
                return 0 if path == owned_file else 998

            with patch("output.delivery_health._path_uid", side_effect=fake_uid):
                health = build_weekly_delivery_health(
                    project_root=root,
                    now=datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc),
                    timer_runner=_active_timer_runner,
                )

        rendered = "\n".join(format_weekly_delivery_health(health, relative_to=root))
        self.assertIn("root_owned_output_paths", health.failure_reasons)
        self.assertIn("root_owned_output_paths: count=1", rendered)
        self.assertIn("data/output/weekly_intelligence_briefs/2026-W28.weekly-brief.html", rendered)


if __name__ == "__main__":
    unittest.main()
