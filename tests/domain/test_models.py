"""
Unit tests for zeiterfassung/domain/models.py

Tests for data class construction, Settings validation, exception hierarchy.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import (
    DayResult,
    DuplicateEntryError,
    EntryType,
    MissingDay,
    TimeEntry,
)

_NOW = datetime.datetime(2026, 4, 7, 9, 0, 0)


class TestTimeEntry:
    """Tests for the TimeEntry dataclass."""

    def test_note_accepts_none(self):
        """TimeEntry.note defaults to None without error (MIN-002)."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.sick,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.note is None

    def test_note_accepts_string(self):
        """TimeEntry.note accepts a non-None string."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.sick,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
            note="doctor visit",
        )
        assert entry.note == "doctor visit"

    def test_id_defaults_to_none(self):
        """New TimeEntry has id=None before persistence."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            pause_minutes=30,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.id is None


class TestDayResult:
    """Tests for DayResult."""

    def test_missing_day_result(self):
        """DayResult with is_missing=True and no entry is valid."""
        result = DayResult(
            date=datetime.date(2026, 4, 7),
            entry=None,
            delta_minutes=-480,
            is_missing=True,
        )
        assert result.is_missing is True
        assert result.entry is None
        assert result.delta_minutes == -480

    def test_present_day_result(self):
        """DayResult with is_missing=False and an entry is valid."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        result = DayResult(date=datetime.date(2026, 4, 7), entry=entry, delta_minutes=0, is_missing=False)
        assert result.is_missing is False
        assert result.entry is entry


class TestMissingDay:
    """Tests for the MissingDay sentinel."""

    def test_missing_day_construction(self):
        """MissingDay is a valid domain sentinel."""
        md = MissingDay(date=datetime.date(2026, 4, 7), daily_target_minutes=480)
        assert md.daily_target_minutes == 480

    def test_missing_day_is_not_time_entry(self):
        """MissingDay is a different type than TimeEntry — they must not be confused."""
        md = MissingDay(date=datetime.date(2026, 4, 7), daily_target_minutes=480)
        assert not isinstance(md, TimeEntry)


class TestSettings:
    """Tests for the Settings dataclass and its computed property."""

    def test_daily_target_40h(self):
        """40h / 5 days * 60 min = 480 minutes per day."""
        s = Settings(weekly_hours=40.0, state="BY")
        assert s.daily_target_minutes == 480

    def test_daily_target_35h(self):
        """35h weekly hours → 420 minutes per day."""
        s = Settings(weekly_hours=35.0, state="BY")
        assert s.daily_target_minutes == 420

    def test_weekly_hours_zero_raises(self):
        """weekly_hours=0 raises ValueError (EC-3)."""
        s = Settings(weekly_hours=0.0, state="BY")
        with pytest.raises(ValueError, match="positive"):
            _ = s.daily_target_minutes

    def test_weekly_hours_negative_raises(self):
        """Negative weekly_hours raises ValueError."""
        s = Settings(weekly_hours=-8.0, state="BY")
        with pytest.raises(ValueError, match="positive"):
            _ = s.daily_target_minutes


class TestDuplicateEntryError:
    """Tests for the DuplicateEntryError exception."""

    def test_is_exception(self):
        """DuplicateEntryError is an Exception subclass."""
        err = DuplicateEntryError("test")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        """DuplicateEntryError can be raised and caught."""
        with pytest.raises(DuplicateEntryError):
            raise DuplicateEntryError("duplicate")
