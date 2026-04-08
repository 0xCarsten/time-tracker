"""
Unit tests for zeiterfassung/domain/holidays.py

Tests for public holiday detection, bundesland validation, and edge cases.
# TODO EC-7: public holiday on DST transition day (e.g. 2032-03-27 in BY)
# requires wall-clock mocking — low testability, skipped at MVP.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.domain.holidays import get_holidays, is_public_holiday
from zeiterfassung.domain.rules import is_workday


class TestGetHolidays:
    """Tests for get_holidays()."""

    def test_christmas_in_bavaria_2026(self):
        """Christmas Day 2026 is in the Bavaria holiday set."""
        holidays = get_holidays(2026, "BY")
        assert datetime.date(2026, 12, 25) in holidays

    def test_new_year_in_bavaria(self):
        """New Year's Day is in the Bavaria holiday set."""
        holidays = get_holidays(2026, "BY")
        assert datetime.date(2026, 1, 1) in holidays

    def test_invalid_state_raises(self):
        """get_holidays with an invalid state code raises ValueError (CRIT-001)."""
        with pytest.raises(ValueError, match="Invalid state"):
            get_holidays(2026, "XX")

    def test_returns_set(self):
        """Return type is a set of date objects."""
        result = get_holidays(2026, "BY")
        assert isinstance(result, set)
        assert all(isinstance(d, datetime.date) for d in result)


class TestIsPublicHoliday:
    """Tests for is_public_holiday()."""

    def test_christmas_is_holiday(self):
        """Christmas Day 2026 is a public holiday in Bavaria."""
        result = is_public_holiday(datetime.date(2026, 12, 25), "BY")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_regular_workday_not_holiday(self):
        """A regular Wednesday returns None (not a holiday)."""
        result = is_public_holiday(datetime.date(2026, 4, 8), "BY")
        assert result is None

    def test_invalid_state_raises(self):
        """Invalid state code raises ValueError — not a print (CRIT-001 / GUD-001)."""
        with pytest.raises(ValueError, match="Invalid state code 'ZZ'"):
            is_public_holiday(datetime.date(2026, 4, 8), "ZZ")

    def test_holiday_on_saturday_not_workday(self):
        """A holiday on Saturday means is_workday returns False (R7)."""
        # Christmas 2021 was on Saturday
        result = is_public_holiday(datetime.date(2021, 12, 25), "BY")
        assert result is not None  # It is a holiday
        assert is_workday(datetime.date(2021, 12, 25), "BY") is False  # But not a workday

    def test_easter_monday_2026(self):
        """Easter Monday 2026 (April 6) is a public holiday in Bavaria."""
        result = is_public_holiday(datetime.date(2026, 4, 6), "BY")
        assert result is not None

    def test_same_day_different_state(self):
        """Corpus Christi is valid in BY but not in all states (e.g. not in HB)."""
        # Corpus Christi 2026 is June 4
        by_result = is_public_holiday(datetime.date(2026, 6, 4), "BY")
        hb_result = is_public_holiday(datetime.date(2026, 6, 4), "HB")
        assert by_result is not None  # Bavaria has Corpus Christi
        assert hb_result is None  # Bremen does not
