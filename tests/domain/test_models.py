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
    IncompleteEntryError,
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
        result = DayResult(
            date=datetime.date(2026, 4, 7),
            entry=entry,
            delta_minutes=0,
            is_missing=False,
        )
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


class TestTimeEntryIsComplete:
    """Tests for TimeEntry.is_complete property (TEST-001)."""

    def test_complete_work_entry_is_complete(self):
        """Work entry with both start_time and end_time is complete."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is True

    def test_work_entry_missing_end_time_is_incomplete(self):
        """Work entry with start_time but no end_time is incomplete."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is False

    def test_work_entry_missing_start_time_is_incomplete(self):
        """Work entry with end_time but no start_time is incomplete (T13 anomaly)."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            start_time=None,
            end_time=datetime.time(17, 0),
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is False

    def test_work_entry_no_times_is_incomplete(self):
        """Work entry with neither start_time nor end_time is incomplete."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            start_time=None,
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is False

    def test_sick_entry_always_complete(self):
        """Non-work entries are always complete regardless of time fields."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.sick,
            start_time=None,
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is True

    def test_vacation_entry_always_complete(self):
        """Vacation entry is always complete."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.vacation,
            start_time=None,
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert entry.is_complete is True


class TestDayResultIsIncomplete:
    """Tests for DayResult.is_incomplete field."""

    def test_is_incomplete_defaults_to_false(self):
        """DayResult.is_incomplete defaults to False (TASK-002)."""
        result = DayResult(
            date=datetime.date(2026, 4, 7),
            entry=None,
            delta_minutes=-480,
            is_missing=True,
        )
        assert result.is_incomplete is False

    def test_is_incomplete_can_be_set_true(self):
        """DayResult.is_incomplete can be explicitly set to True."""
        entry = TimeEntry(
            date=datetime.date(2026, 4, 7),
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=480,
            created_at=_NOW,
            updated_at=_NOW,
        )
        result = DayResult(
            date=datetime.date(2026, 4, 7),
            entry=entry,
            delta_minutes=0,
            is_missing=False,
            is_incomplete=True,
        )
        assert result.is_incomplete is True
        assert result.is_missing is False


class TestIncompleteEntryError:
    """Tests for IncompleteEntryError exception."""

    def test_is_exception(self):
        """IncompleteEntryError is an Exception subclass."""
        err = IncompleteEntryError("missing end time")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        """IncompleteEntryError can be raised and caught independently of ValueError."""
        with pytest.raises(IncompleteEntryError):
            raise IncompleteEntryError("incomplete")
