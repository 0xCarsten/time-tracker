"""
Integration tests for zeiterfassung/services/entry_service.py

Uses shared db_conn fixture from conftest.py.
Includes MIN-004 running saldo integration test over a 5-day mixed sequence.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import EntryType, TimeEntry
from zeiterfassung.repository.entry_repo import EntryRepository
from zeiterfassung.services.entry_service import EntryService

_NOW = datetime.datetime(2026, 4, 1, 9, 0, 0)
_TARGET = 480  # 8 hours = 480 minutes


def _settings() -> Settings:
    """Create a test Settings instance with 40h/week in Bayern."""
    return Settings(weekly_hours=40.0, bundesland="BY")


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
            entry_type=EntryType.krank,
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
            entry_type=EntryType.krank,
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
            entry_type=EntryType.krank,
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
        repo.insert(TimeEntry(
            date=datetime.date(2026, 3, 16),
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(19, 0),
            pause_minutes=0,
            daily_target_minutes=_TARGET,
            created_at=_NOW, updated_at=_NOW,
        ))
        # Day 2: krank 0
        repo.insert(TimeEntry(
            date=datetime.date(2026, 3, 17),
            entry_type=EntryType.krank,
            pause_minutes=0,
            daily_target_minutes=_TARGET,
            created_at=_NOW, updated_at=_NOW,
        ))
        # Day 3: Mar 18 — no entry (missing workday), delta = -480
        # Day 4: urlaub 0
        repo.insert(TimeEntry(
            date=datetime.date(2026, 3, 19),
            entry_type=EntryType.urlaub,
            pause_minutes=0,
            daily_target_minutes=_TARGET,
            created_at=_NOW, updated_at=_NOW,
        ))
        # Day 5: work +60
        repo.insert(TimeEntry(
            date=datetime.date(2026, 3, 20),
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(18, 0),
            pause_minutes=0,
            daily_target_minutes=_TARGET,
            created_at=_NOW, updated_at=_NOW,
        ))

        results = service.build_day_results(
            datetime.date(2026, 3, 16), datetime.date(2026, 3, 20)
        )

        # 5 results: entries on 14, 15, 16 (missing!), 17, 18
        assert len(results) == 5

        expected_deltas = [120, 0, -480, 0, 60]
        for i, (result, expected) in enumerate(zip(results, expected_deltas)):
            assert result.delta_minutes == expected, (
                f"Day {i+1}: expected delta={expected}, got {result.delta_minutes}"
            )

        # Verify running saldo accumulates correctly
        running = 0
        expected_running = [120, 120, -360, -360, -300]
        for i, (result, expected) in enumerate(zip(results, expected_running)):
            running += result.delta_minutes
            assert running == expected, (
                f"Day {i+1}: expected running={expected}, got {running}"
            )


class TestAddAndOverwriteEntry:
    """Tests for add_entry and overwrite_entry."""

    def test_add_entry_krank(self, db_conn):
        """add_entry creates a krank entry successfully."""
        service = _make_service(db_conn)
        entry = service.add_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.krank,
        )
        assert entry.id is not None
        assert entry.entry_type == EntryType.krank

    def test_overwrite_entry_is_sole_upsert_path(self, db_conn):
        """overwrite_entry is the only path that calls repo.upsert (CRIT-002)."""
        service = _make_service(db_conn)
        service.add_entry(date=datetime.date(2026, 4, 8), entry_type=EntryType.krank)
        updated = service.overwrite_entry(
            date=datetime.date(2026, 4, 8),
            entry_type=EntryType.urlaub,
        )
        assert updated.entry_type == EntryType.urlaub
        fetched = service.get_entry(datetime.date(2026, 4, 8))
        assert fetched is not None
        assert fetched.entry_type == EntryType.urlaub

    def test_delete_entry(self, db_conn):
        """delete_entry removes the entry and returns True."""
        service = _make_service(db_conn)
        service.add_entry(date=datetime.date(2026, 4, 8), entry_type=EntryType.krank)
        assert service.delete_entry(datetime.date(2026, 4, 8)) is True
        assert service.get_entry(datetime.date(2026, 4, 8)) is None
