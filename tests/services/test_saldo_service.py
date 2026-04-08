"""
Integration tests for zeiterfassung/services/saldo_service.py

Uses shared db_conn fixture from conftest.py.
Tests cumulative saldo computation with various entry types and missing workdays.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import EntryType, TimeEntry
from zeiterfassung.repository.entry_repo import EntryRepository
from zeiterfassung.services.saldo_service import BalanceService

_NOW = datetime.datetime(2026, 4, 1, 9, 0, 0)
_TARGET = 480  # 8 hours in minutes


def _settings(weekly_hours: float = 40.0, state: str = "BY") -> Settings:
    """Create a test Settings instance."""
    return Settings(weekly_hours=weekly_hours, state=state)


def _insert_work(repo: EntryRepository, date: datetime.date, start: str, end: str, pause: int = 0) -> None:
    """Insert a work entry into the repo."""
    repo.insert(TimeEntry(
        date=date,
        entry_type=EntryType.work,
        start_time=datetime.time.fromisoformat(start),
        end_time=datetime.time.fromisoformat(end),
        pause_minutes=pause,
        daily_target_minutes=_TARGET,
        created_at=_NOW,
        updated_at=_NOW,
    ))


def _insert_sick(repo: EntryRepository, date: datetime.date) -> None:
    """Insert a sick entry into the repo."""
    repo.insert(TimeEntry(
        date=date,
        entry_type=EntryType.sick,
        pause_minutes=0,
        daily_target_minutes=_TARGET,
        created_at=_NOW,
        updated_at=_NOW,
    ))


def _insert_absent(repo: EntryRepository, date: datetime.date) -> None:
    """Insert an absent entry into the repo."""
    repo.insert(TimeEntry(
        date=date,
        entry_type=EntryType.absent,
        pause_minutes=0,
        daily_target_minutes=_TARGET,
        created_at=_NOW,
        updated_at=_NOW,
    ))


class TestSaldoServiceEmpty:
    """Tests for empty DB behaviour."""

    def test_compute_empty_db_returns_zero(self, db_conn):
        """compute() on an empty DB returns 0, never raises (REQ-010)."""
        repo = EntryRepository(db_conn)
        service = BalanceService(repo, _settings())
        assert service.compute() == 0


class TestSaldoServiceWithEntries:
    """Tests for saldo computation with entries."""

    def test_work_overtime(self, db_conn):
        """Work entry with 1-hour overtime contributes +60 to balance."""
        repo = EntryRepository(db_conn)
        # 09:00-18:00 = 9h - 0 pause - 8h target = +60 min
        _insert_work(repo, datetime.date(2026, 4, 8), "09:00", "18:00")
        service = BalanceService(repo, _settings())
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 8),
        )
        assert balance == 60

    def test_sick_zero_delta(self, db_conn):
        """sick entry contributes 0 to balance."""
        repo = EntryRepository(db_conn)
        _insert_sick(repo, datetime.date(2026, 4, 8))
        service = BalanceService(repo, _settings())
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 8),
        )
        assert balance == 0

    def test_absent_negative_target(self, db_conn):
        """absent entry contributes -daily_target to balance."""
        repo = EntryRepository(db_conn)
        _insert_absent(repo, datetime.date(2026, 4, 8))
        service = BalanceService(repo, _settings())
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 8),
        )
        assert balance == -_TARGET

    def test_mixed_entries_sum(self, db_conn):
        """Mix of work, sick, absent computes correct total."""
        repo = EntryRepository(db_conn)
        # Wed Apr 8: work +60, Thu Apr 9: sick 0, Fri Apr 10: absent -480
        _insert_work(repo, datetime.date(2026, 4, 8), "09:00", "18:00")  # +60
        _insert_sick(repo, datetime.date(2026, 4, 9))                     # 0
        _insert_absent(repo, datetime.date(2026, 4, 10))                  # -480
        service = BalanceService(repo, _settings())
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 10),
        )
        assert balance == 60 + 0 + (-480)

    def test_from_to_date_filter(self, db_conn):
        """Date range filter restricts balance computation."""
        repo = EntryRepository(db_conn)
        _insert_work(repo, datetime.date(2026, 4, 8), "09:00", "18:00")  # +60
        _insert_work(repo, datetime.date(2026, 4, 9), "09:00", "18:00")  # +60
        service = BalanceService(repo, _settings())
        # Only include April 8
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 8),
        )
        assert balance == 60


class TestSaldoWithMissingWorkdays:
    """Tests for saldo computation including missing workdays."""

    def test_missing_workday_subtracts_target(self, db_conn):
        """A missing workday in range subtracts daily_target_minutes from balance."""
        repo = EntryRepository(db_conn)
        service = BalanceService(repo, _settings())
        # April 8, 2026 is a Wednesday (workday in BY, no holiday)
        balance = service.compute(
            from_date=datetime.date(2026, 4, 8),
            to_date=datetime.date(2026, 4, 8),
        )
        assert balance == -_TARGET

    def test_weekend_not_subtracted(self, db_conn):
        """Weekend days are NOT counted as missing workdays."""
        repo = EntryRepository(db_conn)
        service = BalanceService(repo, _settings())
        # April 11-12, 2026 is Saturday/Sunday
        balance = service.compute(
            from_date=datetime.date(2026, 4, 11),
            to_date=datetime.date(2026, 4, 12),
        )
        assert balance == 0
