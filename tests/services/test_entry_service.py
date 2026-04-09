"""
Integration tests for zeiterfassung/services/entry_service.py

Uses shared db_conn fixture from conftest.py.
Includes MIN-004 running saldo integration test over a 5-day mixed sequence.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import DuplicateEntryError, EntryType, TimeEntry
from zeiterfassung.repository.entry_repo import EntryRepository
from zeiterfassung.services.entry_service import EntryService

_NOW = datetime.datetime(2026, 4, 1, 9, 0, 0)
_TARGET = 480  # 8 hours = 480 minutes


def _settings() -> Settings:
    """Create a test Settings instance with 40h/week in Bavaria."""
    return Settings(weekly_hours=40.0, state="BY")


def _make_service(db_conn) -> EntryService:
    """Create an EntryService backed by an in-memory DB."""
    return EntryService(EntryRepository(db_conn), _settings())


class TestGetMissingWorkdays:
    """Tests for EntryService.get_missing_workdays."""

    def test_excludes_weekends(self, db_conn):
        """Weekends are not returned as missing workdays."""
        service = _make_service(db_conn)
        # April 11-12 2026 is Saturday/Sunday
        missing = service.get_missing_workdays(
            datetime.date(2026, 4, 11), datetime.date(2026, 4, 12)
        )
        assert missing == []

    def test_excludes_public_holidays(self, db_conn):
        """Public holidays (Easter Monday) are not returned as missing."""
        service = _make_service(db_conn)
        # Easter Monday 2026 is April 6 (Monday but is a holiday in BY)
        missing = service.get_missing_workdays(
            datetime.date(2026, 4, 6), datetime.date(2026, 4, 6)
        )
        assert missing == []

    def test_excludes_dates_with_entries(self, db_conn):
        """Dates with entries are not returned as missing."""
        service = _make_service(db_conn)
        # April 8 is a workday; add an entry for it
        service.add_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.sick,
        )
        missing = service.get_missing_workdays(
            datetime.date(2026, 4, 8), datetime.date(2026, 4, 8)
        )
        assert missing == []

    def test_returns_missing_workday(self, db_conn):
        """A workday with no entry is returned as missing."""
        service = _make_service(db_conn)
        # April 8 is a Wednesday workday; no entry
        missing = service.get_missing_workdays(
            datetime.date(2026, 4, 8), datetime.date(2026, 4, 8)
        )
        assert datetime.date(2026, 4, 8) in missing


class TestBuildDayResults:
    """Tests for EntryService.build_day_results."""

    def test_missing_day_in_results(self, db_conn):
        """build_day_results includes a DayResult with is_missing=True for gaps.

        A day is only missing when it is <= today AND >= the earliest entry in
        the DB (so deleted entries and future days are not flagged as missing).
        We insert an entry on Mar 31 so min_date is set, then ask for Mar 31–Apr 1;
        Apr 1 (Tuesday, past, no entry) should be missing.
        """
        service = _make_service(db_conn)
        # Seed one entry so the tracking window is open
        service.add_entry(
            date=datetime.date(2026, 3, 31),  # Tuesday, past
            entry_type=EntryType.sick,
        )
        results = service.build_day_results(
            datetime.date(2026, 4, 1), datetime.date(2026, 4, 1)
        )
        # Apr 1 is a Wednesday workday in the past with no entry
        assert len(results) == 1
        assert results[0].is_missing is True
        assert results[0].entry is None

    def test_entry_in_results(self, db_conn):
        """build_day_results includes a DayResult with is_missing=False for logged entries."""
        service = _make_service(db_conn)
        service.add_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.sick,
        )
        results = service.build_day_results(
            datetime.date(2026, 4, 8), datetime.date(2026, 4, 8)
        )
        assert len(results) == 1
        assert results[0].is_missing is False
        assert results[0].entry is not None

    def test_running_saldo_integration_min004(self, db_conn):
        """
        MIN-004 running saldo integration test over a 5-day mixed sequence (TASK-034).

        Week Mar 16-20, 2026 (no BY holidays, all dates in the past):
        - Mar 16 Mon: work 09:00-19:00 → delta +120
        - Mar 17 Tue: krank → delta 0
        - Mar 18 Wed: missing workday → delta -480
        - Mar 19 Thu: urlaub → delta 0
        - Mar 20 Fri: work 09:00-18:00 → delta +60

        Expected deltas:        [+120,   0, -480,    0,  +60]
        Expected running saldo: [+120, +120, -360, -360, -300]

        Uses past dates so the missing-day window (>= min_date, <= today) applies.
        """
        service = _make_service(db_conn)
        repo = EntryRepository(db_conn)

        # Day 1: work +120
        repo.insert(
            TimeEntry(
                date=datetime.date(2026, 3, 16),
                entry_type=EntryType.work,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(19, 0),
                pause_minutes=0,
                daily_target_minutes=_TARGET,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        # Day 2: sick 0
        repo.insert(
            TimeEntry(
                date=datetime.date(2026, 3, 17),
                entry_type=EntryType.sick,
                pause_minutes=0,
                daily_target_minutes=_TARGET,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        # Day 3: Mar 18 — no entry (missing workday), delta = -480
        # Day 4: vacation 0
        repo.insert(
            TimeEntry(
                date=datetime.date(2026, 3, 19),
                entry_type=EntryType.vacation,
                pause_minutes=0,
                daily_target_minutes=_TARGET,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        # Day 5: work +60
        repo.insert(
            TimeEntry(
                date=datetime.date(2026, 3, 20),
                entry_type=EntryType.work,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(18, 0),
                pause_minutes=0,
                daily_target_minutes=_TARGET,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )

        results = service.build_day_results(
            datetime.date(2026, 3, 16), datetime.date(2026, 3, 20)
        )

        # 5 results: entries on 14, 15, 16 (missing!), 17, 18
        assert len(results) == 5

        expected_deltas = [120, 0, -480, 0, 60]
        for i, (result, expected) in enumerate(zip(results, expected_deltas)):
            assert (
                result.delta_minutes == expected
            ), f"Day {i+1}: expected delta={expected}, got {result.delta_minutes}"

        # Verify running saldo accumulates correctly
        running = 0
        expected_running = [120, 120, -360, -360, -300]
        for i, (result, expected) in enumerate(zip(results, expected_running)):
            running += result.delta_minutes
            assert (
                running == expected
            ), f"Day {i+1}: expected running={expected}, got {running}"


class TestAddAndOverwriteEntry:
    """Tests for add_entry and overwrite_entry."""

    def test_add_entry_sick(self, db_conn):
        """add_entry creates a sick entry successfully."""
        service = _make_service(db_conn)
        entry = service.add_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.sick,
        )
        assert entry.id is not None
        assert entry.entry_type == EntryType.sick

    def test_overwrite_entry_is_sole_upsert_path(self, db_conn):
        """overwrite_entry is the only path that calls repo.upsert (CRIT-002)."""
        service = _make_service(db_conn)
        service.add_entry(date=datetime.date(2026, 4, 8), entry_type=EntryType.sick)
        updated = service.overwrite_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.vacation,
        )
        assert updated.entry_type == EntryType.vacation
        fetched = service.get_entry(datetime.date(2026, 4, 8))
        assert fetched is not None
        assert fetched.entry_type == EntryType.vacation

    def test_delete_entry(self, db_conn):
        """delete_entry removes the entry and returns True."""
        service = _make_service(db_conn)
        service.add_entry(date=datetime.date(2026, 4, 8), entry_type=EntryType.sick)
        assert service.delete_entry(datetime.date(2026, 4, 8)) is True
        assert service.get_entry(datetime.date(2026, 4, 8)) is None


class TestStartEntry:
    """Tests for EntryService.start_entry (TEST-003, TEST-004)."""

    def test_start_entry_creates_open_work_entry(self, db_conn):
        """start_entry inserts a work entry with start_time set and end_time=None (TEST-003)."""
        service = _make_service(db_conn)
        start_time = datetime.time(9, 0)
        entry = service.start_entry(datetime.date(2026, 4, 8), start_time)

        assert entry.id is not None
        assert entry.entry_type == EntryType.work
        assert entry.start_time == start_time
        assert entry.end_time is None
        assert entry.pause_minutes == 0
        assert entry.is_complete is False

    def test_start_entry_raises_duplicate_for_open_entry(self, db_conn):
        """start_entry raises DuplicateEntryError when open entry already exists (TEST-004)."""
        service = _make_service(db_conn)
        service.start_entry(datetime.date(2026, 4, 8), datetime.time(9, 0))

        with pytest.raises(DuplicateEntryError, match="2026-04-08"):
            service.start_entry(datetime.date(2026, 4, 8), datetime.time(10, 0))

    def test_start_entry_raises_duplicate_for_complete_entry(self, db_conn):
        """start_entry raises DuplicateEntryError when a complete entry already exists (TEST-004)."""
        service = _make_service(db_conn)
        service.add_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.work,
            time_range_raw="09:00-17:00",
        )

        with pytest.raises(DuplicateEntryError):
            service.start_entry(datetime.date(2026, 4, 8), datetime.time(9, 0))

    def test_start_entry_raises_duplicate_for_sick_entry(self, db_conn):
        """start_entry raises DuplicateEntryError for any existing entry type (TEST-004)."""
        service = _make_service(db_conn)
        service.add_entry(date=datetime.date(2026, 4, 8), entry_type=EntryType.sick)

        with pytest.raises(DuplicateEntryError):
            service.start_entry(datetime.date(2026, 4, 8), datetime.time(9, 0))


class TestStopEntry:
    """Tests for EntryService.stop_entry (TEST-005 to TEST-008, TEST-018, TEST-019)."""

    def _open_entry(
        self, service: "EntryService", date: datetime.date, start: str
    ) -> None:
        """Helper to create an open work entry via start_entry."""
        service.start_entry(date, datetime.time.fromisoformat(start))

    def test_stop_entry_updates_end_time(self, db_conn):
        """stop_entry sets end_time on an open entry and returns the updated TimeEntry (TEST-005)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        self._open_entry(service, date, "09:00")

        end_time = datetime.time(17, 0)
        updated = service.stop_entry(date, end_time)

        assert updated.end_time == end_time
        assert updated.start_time == datetime.time(9, 0)
        assert updated.is_complete is True

    def test_stop_entry_sets_pause_minutes(self, db_conn):
        """stop_entry correctly converts pause_decimal to pause_minutes."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        self._open_entry(service, date, "09:00")

        updated = service.stop_entry(date, datetime.time(17, 30), pause_decimal=0.5)
        assert updated.pause_minutes == 30

    def test_stop_entry_raises_if_no_entry(self, db_conn):
        """stop_entry raises ValueError if no entry exists for date (TEST-006)."""
        service = _make_service(db_conn)
        with pytest.raises(ValueError, match="zeit start"):
            service.stop_entry(datetime.date(2026, 4, 8), datetime.time(17, 0))

    def test_stop_entry_raises_if_already_complete(self, db_conn):
        """stop_entry raises ValueError if entry is already complete (TEST-007)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        service.add_entry(
            date=date, entry_type=EntryType.work, time_range_raw="09:00-17:00"
        )

        with pytest.raises(ValueError, match="already complete"):
            service.stop_entry(date, datetime.time(18, 0))

    def test_stop_entry_raises_if_not_work_entry(self, db_conn):
        """stop_entry raises ValueError if existing entry is not a work entry (TEST-008)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        service.add_entry(date=date, entry_type=EntryType.sick)

        with pytest.raises(ValueError, match="zeit start"):
            service.stop_entry(date, datetime.time(17, 0))

    def test_stop_entry_raises_if_end_before_start(self, db_conn):
        """stop_entry raises ValueError when end_time < start_time (TEST-018)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        self._open_entry(service, date, "17:00")

        with pytest.raises(ValueError, match="End time is before start time"):
            service.stop_entry(date, datetime.time(8, 0))

    def test_stop_entry_raises_if_pause_exceeds_elapsed(self, db_conn):
        """stop_entry raises ValueError when pause exceeds elapsed time (TEST-019)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        self._open_entry(service, date, "09:00")

        # Elapsed = 17:30 - 09:00 = 8.5h = 510 min; pause = 10h = 600 min → effective < 0
        with pytest.raises(ValueError, match="pause exceeds elapsed time"):
            service.stop_entry(date, datetime.time(17, 30), pause_decimal=10.0)

    def test_stop_entry_raises_if_end_equals_start(self, db_conn):
        """stop_entry raises ValueError when end_time == start_time (effective_minutes = 0)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        self._open_entry(service, date, "09:00")

        with pytest.raises(ValueError, match="End time is before start time"):
            service.stop_entry(date, datetime.time(9, 0))


class TestBuildDayResultsIncomplete:
    """Tests for build_day_results with incomplete (open) work entries (TEST-009)."""

    def test_incomplete_entry_yields_is_incomplete_flag(self, db_conn):
        """build_day_results returns is_incomplete=True and delta_minutes=0 for open entry (TEST-009)."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        service.start_entry(date, datetime.time(9, 0))

        results = service.build_day_results(date, date)
        assert len(results) == 1
        result = results[0]
        assert result.is_incomplete is True
        assert result.delta_minutes == 0
        assert result.is_missing is False
        assert result.entry is not None

    def test_complete_entry_is_not_incomplete(self, db_conn):
        """build_day_results returns is_incomplete=False for a fully complete work entry."""
        service = _make_service(db_conn)
        date = datetime.date(2026, 4, 8)
        service.add_entry(
            date=date, entry_type=EntryType.work, time_range_raw="09:00-17:00"
        )

        results = service.build_day_results(date, date)
        assert len(results) == 1
        assert results[0].is_incomplete is False
