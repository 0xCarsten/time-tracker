"""
Unit tests for zeiterfassung/domain/rules.py

Tests delta calculation per type, time parsing, workday detection, and edge cases.
No DB fixtures needed — pure domain functions.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.domain.models import EntryType, TimeEntry
from zeiterfassung.domain.rules import (
    calculate_delta,
    decimal_hours_to_minutes,
    is_workday,
    parse_time_range,
)

_NOW = datetime.datetime(2026, 4, 7, 9, 0, 0)
_TARGET = 480  # 8 hours = 480 minutes


def _make_entry(
    entry_type: EntryType,
    start: str | None = None,
    end: str | None = None,
    pause_minutes: int = 0,
    daily_target: int = _TARGET,
) -> TimeEntry:
    """Helper to build a TimeEntry for testing."""
    return TimeEntry(
        date=datetime.date(2026, 4, 7),
        entry_type=entry_type,
        start_time=datetime.time.fromisoformat(start) if start else None,
        end_time=datetime.time.fromisoformat(end) if end else None,
        pause_minutes=pause_minutes,
        daily_target_minutes=daily_target,
        created_at=_NOW,
        updated_at=_NOW,
    )


# ---------------------------------------------------------------------------
# calculate_delta tests
# ---------------------------------------------------------------------------


class TestCalculateDelta:
    """Tests for calculate_delta with each entry type."""

    def test_work_exact_target(self):
        """Work entry exactly matching daily target: (480 - 0) - 480 = 0 (TEST-002)."""
        entry = _make_entry(EntryType.work, start="09:00", end="17:00", pause_minutes=0)
        assert calculate_delta(entry) == 0

    def test_work_overtime(self):
        """Work entry with 1 hour overtime."""
        entry = _make_entry(EntryType.work, start="09:00", end="18:00", pause_minutes=0)
        assert calculate_delta(entry) == 60  # 540 - 480 = 60

    def test_work_with_pause(self):
        """Work with 30-minute pause: (540 - 30) - 480 = 30 min overtime."""
        entry = _make_entry(EntryType.work, start="09:00", end="18:00", pause_minutes=30)
        assert calculate_delta(entry) == 30

    def test_work_undertime(self):
        """Work entry shorter than target — negative delta."""
        entry = _make_entry(EntryType.work, start="09:00", end="16:00", pause_minutes=0)
        assert calculate_delta(entry) == -60  # 420 - 480 = -60

    def test_krank_zero_delta(self):
        """krank entry always returns delta 0."""
        entry = _make_entry(EntryType.krank)
        assert calculate_delta(entry) == 0

    def test_urlaub_zero_delta(self):
        """urlaub entry always returns delta 0."""
        entry = _make_entry(EntryType.urlaub)
        assert calculate_delta(entry) == 0

    def test_feiertag_zero_delta(self):
        """feiertag entry always returns delta 0."""
        entry = _make_entry(EntryType.feiertag)
        assert calculate_delta(entry) == 0

    def test_abwesend_negative_target(self):
        """abwesend entry returns -daily_target_minutes."""
        entry = _make_entry(EntryType.abwesend)
        assert calculate_delta(entry) == -_TARGET

    def test_work_overnight_shift(self):
        """Overnight shift (end < start) must compute positive effective time (EC-1)."""
        # 22:00 to 06:00 = 8 hours, zero pause, target 480 min → delta = 0
        entry = _make_entry(EntryType.work, start="22:00", end="06:00", pause_minutes=0)
        assert calculate_delta(entry) == 0

    def test_work_negative_effective_time_raises(self):
        """Pause longer than work duration must raise ValueError (EC-2)."""
        # 09:00 to 10:00 = 60 min, pause = 90 min → effective = -30
        entry = _make_entry(EntryType.work, start="09:00", end="10:00", pause_minutes=90)
        with pytest.raises(ValueError, match="negative"):
            calculate_delta(entry)

    def test_work_zero_pause(self):
        """Work entry with zero pause handled correctly (EC-1 variant)."""
        entry = _make_entry(EntryType.work, start="09:00", end="17:00", pause_minutes=0)
        assert calculate_delta(entry) == 0


# ---------------------------------------------------------------------------
# parse_time_range tests
# ---------------------------------------------------------------------------


class TestParseTimeRange:
    """Tests for the centralised time range parser (GUD-003)."""

    def test_valid_range(self):
        """Standard work-day range parsed correctly."""
        start, end = parse_time_range("09:00-17:30")
        assert start == datetime.time(9, 0)
        assert end == datetime.time(17, 30)

    def test_overnight_range(self):
        """Overnight range parsed — end time is next day (no validation at parse level)."""
        start, end = parse_time_range("22:00-06:00")
        assert start == datetime.time(22, 0)
        assert end == datetime.time(6, 0)

    def test_invalid_format_no_dash(self):
        """Missing dash raises ValueError."""
        with pytest.raises(ValueError, match="HH:MM-HH:MM"):
            parse_time_range("0900-1700")

    def test_invalid_format_garbage(self):
        """Completely invalid string raises ValueError."""
        with pytest.raises(ValueError):
            parse_time_range("not-a-time")

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is handled."""
        start, end = parse_time_range(" 08:00-16:00 ")
        assert start == datetime.time(8, 0)
        assert end == datetime.time(16, 0)


# ---------------------------------------------------------------------------
# decimal_hours_to_minutes tests
# ---------------------------------------------------------------------------


class TestDecimalHoursToMinutes:
    """Tests for pause/duration conversion from decimal hours to integer minutes."""

    def test_zero(self):
        """Zero hours = zero minutes."""
        assert decimal_hours_to_minutes(0.0) == 0

    def test_one_and_half(self):
        """1.5 hours = 90 minutes."""
        assert decimal_hours_to_minutes(1.5) == 90

    def test_quarter(self):
        """0.25 hours = 15 minutes."""
        assert decimal_hours_to_minutes(0.25) == 15

    def test_full_hour(self):
        """1.0 hour = 60 minutes."""
        assert decimal_hours_to_minutes(1.0) == 60


# ---------------------------------------------------------------------------
# is_workday tests
# ---------------------------------------------------------------------------


class TestIsWorkday:
    """Tests for workday detection (GUD-004)."""

    def test_monday_is_workday(self):
        """Regular Monday is a workday (April 13 is the first non-holiday Monday after Easter 2026)."""
        assert is_workday(datetime.date(2026, 4, 13), "BY") is True

    def test_saturday_is_not_workday(self):
        """Saturday is not a workday."""
        assert is_workday(datetime.date(2026, 4, 11), "BY") is False

    def test_sunday_is_not_workday(self):
        """Sunday is not a workday."""
        assert is_workday(datetime.date(2026, 4, 12), "BY") is False

    def test_easter_monday_bavaria_not_workday(self):
        """Easter Monday 2026 (April 6) is a holiday in Bavaria — not a workday."""
        # Easter Monday 2026 is April 6
        assert is_workday(datetime.date(2026, 4, 6), "BY") is False

    def test_good_friday_bavaria_not_workday(self):
        """Good Friday 2026 is a holiday in Bavaria."""
        # Good Friday 2026 is April 3
        assert is_workday(datetime.date(2026, 4, 3), "BY") is False

    def test_fronleichnam_bavaria_not_workday(self):
        """Fronleichnam 2026 (June 4) is a holiday in Bavaria."""
        assert is_workday(datetime.date(2026, 6, 4), "BY") is False

    def test_holiday_on_weekend_returns_false(self):
        """A holiday on Saturday returns False (R7 — no compensatory day)."""
        # Christmas 2021 was on Saturday
        assert is_workday(datetime.date(2021, 12, 25), "BY") is False

    def test_ec10_leap_year_feb29_is_workday(self):
        """Feb 29, 2028 is a Wednesday — a valid leap-year workday (EC-10, MIN-001)."""
        assert is_workday(datetime.date(2028, 2, 29), "BY") is True

    def test_regular_workday_not_holiday(self):
        """A regular Wednesday with no holiday is a workday."""
        assert is_workday(datetime.date(2026, 4, 8), "BY") is True
