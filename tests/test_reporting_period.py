import sys
import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from output.reporting_period import (
    COMPLETED_ISO_WEEK,
    EXPLICIT_ISO_WEEK,
    PARTIAL_ISO_WEEK,
    TRAILING_SEVEN_DAYS,
    ReportingPeriod,
    ReportingPeriodError,
    format_human_period_label,
    format_inclusive_date_range_ru,
    format_period_display_label,
    register_reporting_period_sqlite,
    resolve_reporting_period,
)


UTC = timezone.utc


class ReportingPeriodTests(unittest.TestCase):
    def test_monday_run_resolves_last_completed_iso_week(self) -> None:
        period = resolve_reporting_period(datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC))

        self.assertEqual(period.run_date.isoformat(), "2026-07-13")
        self.assertEqual(period.generated_at, datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC))
        self.assertEqual(period.analysis_period_start, datetime(2026, 7, 6, tzinfo=UTC))
        self.assertEqual(period.analysis_period_end, datetime(2026, 7, 13, tzinfo=UTC))
        self.assertEqual(period.reporting_week, "2026-W28")
        self.assertEqual(period.week_label, "2026-W28")
        self.assertEqual(period.period_mode, COMPLETED_ISO_WEEK)
        self.assertEqual(period.human_date_label_ru, "6-12 июля 2026")

    def test_sunday_and_monday_do_not_select_an_incomplete_week(self) -> None:
        sunday = resolve_reporting_period(datetime(2026, 7, 12, 23, 59, 59, tzinfo=UTC))
        monday = resolve_reporting_period(datetime(2026, 7, 13, 0, 0, 0, tzinfo=UTC))

        self.assertEqual(sunday.reporting_week, "2026-W27")
        self.assertEqual(sunday.analysis_period_start, datetime(2026, 6, 29, tzinfo=UTC))
        self.assertEqual(sunday.analysis_period_end, datetime(2026, 7, 6, tzinfo=UTC))
        self.assertEqual(monday.reporting_week, "2026-W28")
        self.assertEqual(monday.analysis_period_start, datetime(2026, 7, 6, tzinfo=UTC))
        self.assertEqual(monday.analysis_period_end, datetime(2026, 7, 13, tzinfo=UTC))

    def test_iso_year_boundary_uses_iso_year_not_calendar_year(self) -> None:
        period = resolve_reporting_period(datetime(2021, 1, 4, 8, 0, tzinfo=UTC))

        self.assertEqual(period.reporting_week, "2020-W53")
        self.assertEqual(period.analysis_period_start, datetime(2020, 12, 28, tzinfo=UTC))
        self.assertEqual(period.analysis_period_end, datetime(2021, 1, 4, tzinfo=UTC))
        self.assertEqual(period.human_date_label_ru, "28 декабря 2020 - 3 января 2021")

    def test_explicit_historical_week_handles_standard_calendar_leap_day(self) -> None:
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC),
            week_label="2024-W09",
        )

        self.assertEqual(period.period_mode, EXPLICIT_ISO_WEEK)
        self.assertEqual(period.analysis_period_start, datetime(2024, 2, 26, tzinfo=UTC))
        self.assertEqual(period.analysis_period_end, datetime(2024, 3, 4, tzinfo=UTC))
        self.assertLess(period.analysis_period_start, datetime(2024, 2, 29, 12, tzinfo=UTC))
        self.assertGreater(period.analysis_period_end, datetime(2024, 2, 29, 12, tzinfo=UTC))
        self.assertEqual(period.human_date_label_ru, "26 февраля - 3 марта 2024")

    def test_reporting_week_and_week_label_are_compatible_input_aliases(self) -> None:
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC)
        canonical = resolve_reporting_period(generated_at, reporting_week="2026-W28")
        both = resolve_reporting_period(
            generated_at,
            reporting_week="2026-W28",
            week_label="2026-W28",
        )

        self.assertEqual(canonical, both)
        self.assertEqual(canonical.week_label, canonical.reporting_week)

    def test_current_and_future_explicit_weeks_are_rejected(self) -> None:
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC)

        with self.assertRaisesRegex(ReportingPeriodError, "incomplete or in the future"):
            resolve_reporting_period(generated_at, week_label="2026-W29")
        with self.assertRaisesRegex(ReportingPeriodError, "incomplete or in the future"):
            resolve_reporting_period(generated_at, week_label="2026-W30")

    def test_invalid_or_conflicting_explicit_week_is_rejected(self) -> None:
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC)

        with self.assertRaisesRegex(ReportingPeriodError, "YYYY-Www"):
            resolve_reporting_period(generated_at, week_label="2026-W9")
        with self.assertRaisesRegex(ReportingPeriodError, "invalid ISO week"):
            resolve_reporting_period(generated_at, week_label="2026-W54")
        with self.assertRaisesRegex(ReportingPeriodError, "must match"):
            resolve_reporting_period(
                generated_at,
                week_label="2026-W27",
                reporting_week="2026-W28",
            )

    def test_partial_current_week_is_diagnostic_opt_in(self) -> None:
        generated_at = datetime(2026, 7, 15, 11, 30, 45, tzinfo=UTC)
        period = resolve_reporting_period(generated_at, period_mode=PARTIAL_ISO_WEEK)

        self.assertEqual(period.period_mode, PARTIAL_ISO_WEEK)
        self.assertEqual(period.reporting_week, "2026-W29")
        self.assertEqual(period.analysis_period_start, datetime(2026, 7, 13, tzinfo=UTC))
        self.assertEqual(period.analysis_period_end, generated_at)
        self.assertEqual(period.human_date_label_ru, "13-15 июля 2026")

        with self.assertRaisesRegex(ReportingPeriodError, "current ISO week"):
            resolve_reporting_period(
                generated_at,
                week_label="2026-W28",
                period_mode=PARTIAL_ISO_WEEK,
            )

    def test_trailing_seven_days_uses_exact_boundaries_and_a_distinct_mode(self) -> None:
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC)
        period = resolve_reporting_period(generated_at, period_mode=TRAILING_SEVEN_DAYS)

        self.assertEqual(period.period_mode, TRAILING_SEVEN_DAYS)
        self.assertEqual(period.analysis_period_start, datetime(2026, 7, 6, 7, 2, 52, tzinfo=UTC))
        self.assertEqual(period.analysis_period_end, generated_at)
        self.assertEqual(period.human_date_label_ru, "6-13 июля 2026")
        self.assertNotEqual(period.period_mode, COMPLETED_ISO_WEEK)

        with self.assertRaisesRegex(ReportingPeriodError, "does not accept --week"):
            resolve_reporting_period(
                generated_at,
                week_label="2026-W28",
                period_mode=TRAILING_SEVEN_DAYS,
            )

    def test_trailing_mode_keeps_generation_week_as_compatibility_alias(self) -> None:
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 0, 0, tzinfo=UTC),
            period_mode=TRAILING_SEVEN_DAYS,
        )

        self.assertEqual(period.reporting_week, "2026-W29")
        self.assertEqual(period.week_label, "2026-W29")
        self.assertEqual(period.period_mode, TRAILING_SEVEN_DAYS)
        self.assertEqual(
            format_period_display_label(
                period_mode=period.period_mode,
                reporting_week=period.reporting_week,
                analysis_period_start=period.analysis_period_start,
                analysis_period_end=period.analysis_period_end,
            ),
            "trailing seven days [2026-07-06T00:00:00Z, 2026-07-13T00:00:00Z)",
        )
        self.assertEqual(
            format_human_period_label(
                period_mode=period.period_mode,
                reporting_week=period.reporting_week,
                analysis_period_start=period.analysis_period_start,
                analysis_period_end=period.analysis_period_end,
            ),
            "6-12 июля 2026 · trailing_seven_days",
        )

    def test_partial_display_label_names_mode_and_exact_window(self) -> None:
        period = resolve_reporting_period(
            datetime(2026, 7, 15, 11, 30, tzinfo=UTC),
            period_mode=PARTIAL_ISO_WEEK,
        )

        label = format_period_display_label(
            period_mode=period.period_mode,
            reporting_week=period.reporting_week,
            analysis_period_start=period.analysis_period_start,
            analysis_period_end=period.analysis_period_end,
        )
        self.assertEqual(
            label,
            "partial ISO week 2026-W29 [2026-07-13T00:00:00Z, 2026-07-15T11:30:00Z)",
        )
        self.assertEqual(
            format_human_period_label(
                period_mode=period.period_mode,
                reporting_week=period.reporting_week,
                analysis_period_start=period.analysis_period_start,
                analysis_period_end=period.analysis_period_end,
            ),
            "13-15 июля 2026 · partial_iso_week (2026-W29)",
        )

    def test_generation_time_is_normalized_to_utc_without_losing_precision(self) -> None:
        period = resolve_reporting_period(generated_at="2026-07-13T09:02:52.987654+02:00")

        self.assertEqual(
            period.to_dict(),
            {
                "run_date": "2026-07-13",
                "generated_at": "2026-07-13T07:02:52.987654Z",
                "analysis_period_start": "2026-07-06T00:00:00Z",
                "analysis_period_end": "2026-07-13T00:00:00Z",
                "reporting_week": "2026-W28",
                "week_label": "2026-W28",
                "period_mode": "completed_iso_week",
            },
        )
        self.assertEqual(period.as_dict(), period.to_dict())

    def test_seconds_only_generation_time_keeps_compatibility_format(self) -> None:
        period = resolve_reporting_period(generated_at="2026-07-13T07:02:52Z")

        self.assertEqual(period.to_dict()["generated_at"], "2026-07-13T07:02:52Z")

    def test_sqlite_period_comparison_preserves_microsecond_half_open_boundaries(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            register_reporting_period_sqlite(connection)
            row = connection.execute(
                """
                SELECT
                    reporting_utc_micros(?) < reporting_utc_micros(?),
                    reporting_utc_micros(?) < reporting_utc_micros(?),
                    reporting_utc_micros(?) = reporting_utc_micros(?),
                    reporting_utc_micros(?) IS NULL
                """,
                (
                    "2026-07-12T23:59:59.999999Z",
                    "2026-07-13T00:00:00Z",
                    "2026-07-13T00:00:00Z",
                    "2026-07-13T00:00:00Z",
                    "2026-07-13T02:00:00.000001+02:00",
                    "2026-07-13T00:00:00.000001Z",
                    "2026-07-13T00:00:00",
                ),
            ).fetchone()

        self.assertEqual(row, (1, 0, 1, 1))

    def test_naive_generation_time_is_rejected_instead_of_assuming_local_time(self) -> None:
        with self.assertRaisesRegex(ReportingPeriodError, "explicit timezone"):
            resolve_reporting_period(datetime(2026, 7, 13, 7, 2, 52))

    def test_reporting_period_is_immutable(self) -> None:
        period = resolve_reporting_period(datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC))

        with self.assertRaises(FrozenInstanceError):
            period.reporting_week = "2026-W27"  # type: ignore[misc]

    def test_constructor_rejects_future_or_misaligned_explicit_period(self) -> None:
        with self.assertRaisesRegex(ReportingPeriodError, "incomplete or in the future"):
            ReportingPeriod(
                run_date=date(2026, 7, 13),
                generated_at=datetime(2026, 7, 13, 7, tzinfo=UTC),
                analysis_period_start=datetime(2026, 7, 13, tzinfo=UTC),
                analysis_period_end=datetime(2026, 7, 20, tzinfo=UTC),
                reporting_week="2026-W29",
                period_mode=EXPLICIT_ISO_WEEK,
            )

        with self.assertRaisesRegex(ReportingPeriodError, "boundaries must match"):
            ReportingPeriod(
                run_date=date(2026, 7, 20),
                generated_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
                analysis_period_start=datetime(2026, 7, 7, tzinfo=UTC),
                analysis_period_end=datetime(2026, 7, 13, tzinfo=UTC),
                reporting_week="2026-W28",
                period_mode=EXPLICIT_ISO_WEEK,
            )

    def test_constructor_rejects_mode_specific_boundary_mismatches(self) -> None:
        generated_at = datetime(2026, 7, 15, 11, 30, 45, 123456, tzinfo=UTC)
        with self.assertRaisesRegex(ReportingPeriodError, "end exactly at generated_at"):
            ReportingPeriod(
                run_date=generated_at.date(),
                generated_at=generated_at,
                analysis_period_start=datetime(2026, 7, 13, tzinfo=UTC),
                analysis_period_end=generated_at.replace(microsecond=0),
                reporting_week="2026-W29",
                period_mode=PARTIAL_ISO_WEEK,
            )

        with self.assertRaisesRegex(ReportingPeriodError, "exact seven days"):
            ReportingPeriod(
                run_date=generated_at.date(),
                generated_at=generated_at,
                analysis_period_start=generated_at - timedelta(days=6),
                analysis_period_end=generated_at,
                reporting_week="2026-W29",
                period_mode=TRAILING_SEVEN_DAYS,
            )

        with self.assertRaisesRegex(ReportingPeriodError, "last fully completed"):
            ReportingPeriod(
                run_date=date(2026, 7, 13),
                generated_at=datetime(2026, 7, 13, 7, tzinfo=UTC),
                analysis_period_start=datetime(2026, 6, 29, tzinfo=UTC),
                analysis_period_end=datetime(2026, 7, 6, tzinfo=UTC),
                reporting_week="2026-W27",
                period_mode=COMPLETED_ISO_WEEK,
            )

    def test_inclusive_date_helper_handles_midnight_end_and_partial_day(self) -> None:
        self.assertEqual(
            format_inclusive_date_range_ru(
                datetime(2026, 7, 6, tzinfo=UTC),
                datetime(2026, 7, 13, tzinfo=UTC),
            ),
            "6-12 июля 2026",
        )
        self.assertEqual(
            format_inclusive_date_range_ru(
                datetime(2026, 7, 13, tzinfo=UTC),
                datetime(2026, 7, 13, 7, 2, 52, tzinfo=UTC),
            ),
            "13 июля 2026",
        )


if __name__ == "__main__":
    unittest.main()
