"""Shared UTC reporting-period semantics for intelligence artifacts."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal


COMPLETED_ISO_WEEK = "completed_iso_week"
EXPLICIT_ISO_WEEK = "explicit_iso_week"
TRAILING_SEVEN_DAYS = "trailing_seven_days"
PARTIAL_ISO_WEEK = "partial_iso_week"

PeriodMode = Literal[
    "completed_iso_week",
    "explicit_iso_week",
    "trailing_seven_days",
    "partial_iso_week",
]
REPORTING_PERIOD_MODES = frozenset(
    {
        COMPLETED_ISO_WEEK,
        EXPLICIT_ISO_WEEK,
        TRAILING_SEVEN_DAYS,
        PARTIAL_ISO_WEEK,
    }
)

SQLITE_UTC_MICROS_FUNCTION = "reporting_utc_micros"
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_ISO_WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")
_RUSSIAN_MONTHS_GENITIVE = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


class ReportingPeriodError(ValueError):
    """Raised when a requested reporting period is ambiguous or incomplete."""


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    """Immutable analysis interval with UTC, half-open boundary semantics.

    Datetime fields are timezone-aware UTC values. ``analysis_period_start`` is
    inclusive and ``analysis_period_end`` is exclusive. ``week_label`` remains
    a read-only compatibility alias for ``reporting_week``.
    """

    run_date: date
    generated_at: datetime
    analysis_period_start: datetime
    analysis_period_end: datetime
    reporting_week: str
    period_mode: PeriodMode

    def __post_init__(self) -> None:
        generated_at = _normalize_utc(self.generated_at, field_name="generated_at")
        period_start = _normalize_utc(
            self.analysis_period_start,
            field_name="analysis_period_start",
        )
        period_end = _normalize_utc(
            self.analysis_period_end,
            field_name="analysis_period_end",
        )
        if self.run_date != generated_at.date():
            raise ReportingPeriodError("run_date must be derived from generated_at in UTC")
        if period_end < period_start:
            raise ReportingPeriodError("analysis_period_end must not precede analysis_period_start")
        mode = str(self.period_mode)
        if mode not in REPORTING_PERIOD_MODES:
            raise ReportingPeriodError(f"unsupported period_mode: {self.period_mode!r}")
        reporting_week = str(self.reporting_week)
        week_start, week_end = _iso_week_bounds(reporting_week)

        if mode == COMPLETED_ISO_WEEK:
            current_week_start = _midnight_utc(_start_of_iso_week(generated_at.date()))
            expected_start = current_week_start - timedelta(days=7)
            expected_week = _iso_week_label(expected_start.date())
            if (
                reporting_week != expected_week
                or period_start != expected_start
                or period_end != current_week_start
            ):
                raise ReportingPeriodError(
                    "completed_iso_week must be the last fully completed ISO week at generated_at"
                )
        elif mode == EXPLICIT_ISO_WEEK:
            if period_start != week_start or period_end != week_end:
                raise ReportingPeriodError(
                    "explicit_iso_week boundaries must match reporting_week exactly"
                )
            if period_end > generated_at:
                raise ReportingPeriodError(
                    f"explicit ISO week {reporting_week} is incomplete or in the future"
                )
        elif mode == PARTIAL_ISO_WEEK:
            current_week = _iso_week_label(generated_at.date())
            if reporting_week != current_week or period_start != week_start:
                raise ReportingPeriodError(
                    "partial_iso_week must start at the current ISO week's UTC boundary"
                )
            if period_end != generated_at:
                raise ReportingPeriodError(
                    "partial_iso_week must end exactly at generated_at"
                )
        else:
            if period_end != generated_at or period_start != period_end - timedelta(days=7):
                raise ReportingPeriodError(
                    "trailing_seven_days must be the exact seven days ending at generated_at"
                )
            if reporting_week != _iso_week_label(generated_at.date()):
                raise ReportingPeriodError(
                    "trailing_seven_days reporting_week must retain the generation-week alias"
                )

        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "analysis_period_start", period_start)
        object.__setattr__(self, "analysis_period_end", period_end)

    @property
    def week_label(self) -> str:
        """Compatibility alias retained for V1 report consumers."""

        return self.reporting_week

    @property
    def human_date_label_ru(self) -> str:
        """Inclusive reader-facing dates, for example ``6-12 июля 2026``."""

        return format_inclusive_date_range_ru(
            self.analysis_period_start,
            self.analysis_period_end,
        )

    def to_dict(self) -> dict[str, str]:
        """Serialize period identity for additive report contexts/sidecars."""

        return {
            "run_date": self.run_date.isoformat(),
            "generated_at": _isoformat_utc(self.generated_at),
            "analysis_period_start": _isoformat_utc(self.analysis_period_start),
            "analysis_period_end": _isoformat_utc(self.analysis_period_end),
            "reporting_week": self.reporting_week,
            "week_label": self.week_label,
            "period_mode": self.period_mode,
        }

    def as_dict(self) -> dict[str, str]:
        """Alias for callers that use ``as_dict`` for typed value objects."""

        return self.to_dict()


def resolve_reporting_period(
    now: datetime | str | None = None,
    *,
    generated_at: datetime | str | None = None,
    week_label: str | None = None,
    reporting_week: str | None = None,
    period_mode: PeriodMode | str | None = None,
) -> ReportingPeriod:
    """Resolve one reporting period without relying on local time.

    With no explicit week or mode, the result is the last fully completed ISO
    week. Supplying ``week_label``/``reporting_week`` selects a completed
    historical ISO week. The current week is available only through the
    diagnostic ``partial_iso_week`` mode. ``trailing_seven_days`` is an exact
    rolling interval ending at generation time and is always labeled by its
    distinct mode.

    ``now`` is the test/caller-friendly generation-time argument;
    ``generated_at`` is an equivalent contract-named alias. Supplying both is
    rejected so run identity cannot become ambiguous.
    """

    if now is not None and generated_at is not None:
        raise ReportingPeriodError("supply either now or generated_at, not both")
    generated_value = generated_at if generated_at is not None else now
    if generated_value is None:
        generated_value = datetime.now(timezone.utc)
    resolved_generated_at = _normalize_utc(generated_value, field_name="generated_at")

    requested_week = _resolve_week_aliases(week_label, reporting_week)
    if period_mode is None:
        mode = EXPLICIT_ISO_WEEK if requested_week is not None else COMPLETED_ISO_WEEK
    else:
        mode = str(period_mode).strip()
        if mode not in REPORTING_PERIOD_MODES:
            raise ReportingPeriodError(f"unsupported period_mode: {period_mode!r}")

    if mode == COMPLETED_ISO_WEEK:
        if requested_week is not None:
            raise ReportingPeriodError(
                "completed_iso_week resolves automatically; use explicit_iso_week for --week"
            )
        current_week_start = _start_of_iso_week(resolved_generated_at.date())
        period_end = _midnight_utc(current_week_start)
        period_start = period_end - timedelta(days=7)
        resolved_week = _iso_week_label(period_start.date())
    elif mode == EXPLICIT_ISO_WEEK:
        if requested_week is None:
            raise ReportingPeriodError("explicit_iso_week requires reporting_week or week_label")
        period_start, period_end = _iso_week_bounds(requested_week)
        if period_end > resolved_generated_at:
            raise ReportingPeriodError(
                f"explicit ISO week {requested_week} is incomplete or in the future"
            )
        resolved_week = requested_week
    elif mode == PARTIAL_ISO_WEEK:
        current_week_start = _start_of_iso_week(resolved_generated_at.date())
        current_week = _iso_week_label(current_week_start)
        if requested_week is not None and requested_week != current_week:
            raise ReportingPeriodError(
                "partial_iso_week is diagnostic-only and may select only the current ISO week"
            )
        period_start = _midnight_utc(current_week_start)
        period_end = resolved_generated_at
        resolved_week = current_week
    else:
        if requested_week is not None:
            raise ReportingPeriodError(
                "trailing_seven_days uses exact rolling dates and does not accept --week"
            )
        period_end = resolved_generated_at
        period_start = period_end - timedelta(days=7)
        # Keep the legacy filename/week alias based on generation time. The
        # distinct mode and human date range prevent that compatibility value
        # from claiming ISO-week semantics for the rolling interval.
        resolved_week = _iso_week_label(period_end.date())

    return ReportingPeriod(
        run_date=resolved_generated_at.date(),
        generated_at=resolved_generated_at,
        analysis_period_start=period_start,
        analysis_period_end=period_end,
        reporting_week=resolved_week,
        period_mode=mode,  # type: ignore[arg-type]
    )


def format_inclusive_date_range_ru(
    period_start: datetime | str,
    period_end: datetime | str,
) -> str:
    """Format a UTC half-open interval as inclusive Russian calendar dates."""

    start = _normalize_utc(period_start, field_name="analysis_period_start")
    end = _normalize_utc(period_end, field_name="analysis_period_end")
    if end < start:
        raise ReportingPeriodError("analysis_period_end must not precede analysis_period_start")

    start_date = start.date()
    if end == start:
        inclusive_end_date = start_date
    elif end.timetz().replace(tzinfo=None) == time.min:
        inclusive_end_date = (end - timedelta(days=1)).date()
    else:
        inclusive_end_date = end.date()

    if start_date == inclusive_end_date:
        return _format_date_ru(start_date)
    if start_date.year == inclusive_end_date.year and start_date.month == inclusive_end_date.month:
        return (
            f"{start_date.day}-{inclusive_end_date.day} "
            f"{_RUSSIAN_MONTHS_GENITIVE[inclusive_end_date.month]} {inclusive_end_date.year}"
        )
    if start_date.year == inclusive_end_date.year:
        return (
            f"{start_date.day} {_RUSSIAN_MONTHS_GENITIVE[start_date.month]} - "
            f"{inclusive_end_date.day} {_RUSSIAN_MONTHS_GENITIVE[inclusive_end_date.month]} "
            f"{inclusive_end_date.year}"
        )
    return f"{_format_date_ru(start_date)} - {_format_date_ru(inclusive_end_date)}"


def format_period_display_label(
    *,
    period_mode: str,
    reporting_week: str,
    analysis_period_start: datetime | str,
    analysis_period_end: datetime | str,
) -> str:
    """Return an honest compact label for operator-facing compatibility text."""

    mode = str(period_mode).strip()
    if not mode:
        return str(reporting_week).strip()
    if mode not in REPORTING_PERIOD_MODES:
        raise ReportingPeriodError(f"unsupported period_mode: {period_mode!r}")
    if mode not in {TRAILING_SEVEN_DAYS, PARTIAL_ISO_WEEK}:
        return str(reporting_week).strip()
    start = _normalize_utc(analysis_period_start, field_name="analysis_period_start")
    end = _normalize_utc(analysis_period_end, field_name="analysis_period_end")
    prefix = (
        "trailing seven days"
        if mode == TRAILING_SEVEN_DAYS
        else f"partial ISO week {str(reporting_week).strip()}"
    )
    return f"{prefix} [{_isoformat_utc(start)}, {_isoformat_utc(end)})"


def format_human_period_label(
    *,
    period_mode: str,
    reporting_week: str,
    analysis_period_start: datetime | str,
    analysis_period_end: datetime | str,
) -> str:
    """Format reader-facing inclusive dates with explicit non-weekly modes."""

    label = format_inclusive_date_range_ru(
        analysis_period_start,
        analysis_period_end,
    )
    mode = str(period_mode).strip()
    if mode == TRAILING_SEVEN_DAYS:
        return f"{label} · {TRAILING_SEVEN_DAYS}"
    if mode == PARTIAL_ISO_WEEK:
        return f"{label} · {PARTIAL_ISO_WEEK} ({str(reporting_week).strip()})"
    if mode and mode not in REPORTING_PERIOD_MODES:
        raise ReportingPeriodError(f"unsupported period_mode: {period_mode!r}")
    return label


def register_reporting_period_sqlite(connection: sqlite3.Connection) -> None:
    """Register exact UTC timestamp comparison support on one SQLite connection.

    SQLite's ``julianday()`` rounds fractional seconds to millisecond precision.
    IRX-1 boundaries retain the complete ISO-8601 timestamp, so period-aware
    queries compare integer epoch microseconds instead. Invalid/non-UTC stored
    timestamps map to SQL ``NULL``, matching SQLite's prior non-match behavior
    for an invalid ``julianday`` value.
    """

    connection.create_function(
        SQLITE_UTC_MICROS_FUNCTION,
        1,
        _sqlite_utc_micros,
        deterministic=True,
    )


def reporting_timestamp_sort_key(value: object) -> int:
    """Return an exact UTC ordering key; invalid/non-UTC values sort first."""

    parsed = _try_utc_micros(value)
    return parsed if parsed is not None else -(1 << 63)


def _resolve_week_aliases(week_label: str | None, reporting_week: str | None) -> str | None:
    legacy = str(week_label).strip() if week_label is not None else ""
    canonical = str(reporting_week).strip() if reporting_week is not None else ""
    if legacy and canonical and legacy != canonical:
        raise ReportingPeriodError("week_label and reporting_week must match when both are supplied")
    requested_week = canonical or legacy
    if not requested_week:
        return None
    _iso_week_bounds(requested_week)
    return requested_week


def _sqlite_utc_micros(value: object) -> int | None:
    return _try_utc_micros(value)


def _try_utc_micros(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        parsed = _normalize_utc(str(value), field_name="stored UTC timestamp")
    except ReportingPeriodError:
        return None
    delta = parsed - _UTC_EPOCH
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def _normalize_utc(value: datetime | str, *, field_name: str) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ReportingPeriodError(f"{field_name} must be an ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ReportingPeriodError(f"{field_name} must be a datetime or ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReportingPeriodError(f"{field_name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _iso_week_bounds(week_label: str) -> tuple[datetime, datetime]:
    match = _ISO_WEEK_RE.fullmatch(str(week_label))
    if match is None:
        raise ReportingPeriodError("ISO week must use YYYY-Www format")
    try:
        start_date = date.fromisocalendar(
            int(match.group("year")),
            int(match.group("week")),
            1,
        )
        start = _midnight_utc(start_date)
        return start, start + timedelta(days=7)
    except (OverflowError, ValueError) as exc:
        raise ReportingPeriodError(f"invalid ISO week: {week_label}") from exc


def _start_of_iso_week(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _midnight_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _iso_week_label(value: date) -> str:
    iso_year, iso_week, _ = value.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_date_ru(value: date) -> str:
    return f"{value.day} {_RUSSIAN_MONTHS_GENITIVE[value.month]} {value.year}"
