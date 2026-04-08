"""
Integration tests for zeiterfassung/repository/entry_repo.py

Tests CRUD operations against an in-memory SQLite DB using shared db_conn fixture.
"""

from __future__ import annotations

import datetime

import pytest

from zeiterfassung.domain.models import DuplicateEntryError, EntryType, TimeEntry
from zeiterfassung.repository.db import migrate
from zeiterfassung.repository.entry_repo import EntryRepository

_NOW = datetime.datetime(2026, 4, 1, 9, 0, 0)
_TARGET = 480


def _make_work_entry(
    date: datetime.date = datetime.date(2026, 4, 7),
    note: str | None = None,
) -> TimeEntry:
    """Build a work TimeEntry for testing."""
    return TimeEntry(
        date=date,
        entry_type=EntryType.work,
        start_time=datetime.time(9, 0),
        end_time=datetime.time(17, 0),
        pause_minutes=30,
        daily_target_minutes=_TARGET,
        note=note,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_krank_entry(date: datetime.date = datetime.date(2026, 4, 8)) -> TimeEntry:
    """Build a krank TimeEntry for testing."""
    return TimeEntry(
        date=date,
        entry_type=EntryType.krank,
        pause_minutes=0,
        daily_target_minutes=_TARGET,
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestInsert:
    """Tests for EntryRepository.insert."""

    def test_insert_returns_entry_with_id(self, db_conn):
        """insert() returns the entry with a non-None integer id."""
        repo = EntryRepository(db_conn)
        entry = _make_work_entry()
        result = repo.insert(entry)
        assert result.id is not None
        assert isinstance(result.id, int)
        assert result.id > 0

    def test_insert_duplicate_raises(self, db_conn):
        """insert() raises DuplicateEntryError for same date+type (UNIQUE constraint)."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry())
        with pytest.raises(DuplicateEntryError):
            repo.insert(_make_work_entry())

    def test_insert_different_dates_ok(self, db_conn):
        """Two entries on different dates can be inserted without error."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry(date=datetime.date(2026, 4, 7)))
        repo.insert(_make_work_entry(date=datetime.date(2026, 4, 8)))


class TestGetByDate:
    """Tests for EntryRepository.get_by_date."""

    def test_get_existing_entry(self, db_conn):
        """get_by_date returns the inserted entry."""
        repo = EntryRepository(db_conn)
        original = repo.insert(_make_work_entry())
        fetched = repo.get_by_date(datetime.date(2026, 4, 7))
        assert fetched is not None
        assert fetched.id == original.id
        assert fetched.entry_type == EntryType.work

    def test_get_absent_date_returns_none(self, db_conn):
        """get_by_date returns None for a date with no entry."""
        repo = EntryRepository(db_conn)
        assert repo.get_by_date(datetime.date(2026, 1, 1)) is None

    def test_note_none_roundtrip(self, db_conn):
        """Entry with note=None round-trips as None (not empty string, MIN-002)."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry(note=None))
        fetched = repo.get_by_date(datetime.date(2026, 4, 7))
        assert fetched is not None
        assert fetched.note is None


class TestDeleteByDate:
    """Tests for EntryRepository.delete_by_date."""

    def test_delete_existing_returns_true(self, db_conn):
        """delete_by_date returns True when a row is deleted."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry())
        assert repo.delete_by_date(datetime.date(2026, 4, 7)) is True

    def test_delete_absent_returns_false(self, db_conn):
        """delete_by_date returns False when no row exists."""
        repo = EntryRepository(db_conn)
        assert repo.delete_by_date(datetime.date(2026, 1, 1)) is False

    def test_deleted_entry_not_reachable(self, db_conn):
        """Entry is no longer retrievable after deletion."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry())
        repo.delete_by_date(datetime.date(2026, 4, 7))
        assert repo.get_by_date(datetime.date(2026, 4, 7)) is None


class TestUpsert:
    """Tests for EntryRepository.upsert."""

    def test_upsert_new_entry(self, db_conn):
        """upsert() on a new date creates the entry."""
        repo = EntryRepository(db_conn)
        entry = _make_work_entry()
        result = repo.upsert(entry)
        assert result.id is not None

    def test_upsert_overwrites_existing(self, db_conn):
        """upsert() with a different note overwrites the existing entry."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry(note="original"))
        updated = _make_work_entry(note="updated")
        repo.upsert(updated)
        fetched = repo.get_by_date(datetime.date(2026, 4, 7))
        assert fetched is not None
        assert fetched.note == "updated"


class TestGetRange:
    """Tests for EntryRepository.get_range."""

    def test_get_range_returns_entries(self, db_conn):
        """get_range returns entries within the date range."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry(datetime.date(2026, 4, 7)))
        repo.insert(_make_krank_entry(datetime.date(2026, 4, 8)))

        results = repo.get_range(datetime.date(2026, 4, 7), datetime.date(2026, 4, 8))
        assert len(results) == 2

    def test_get_range_excludes_outside(self, db_conn):
        """get_range excludes entries outside the range."""
        repo = EntryRepository(db_conn)
        repo.insert(_make_work_entry(datetime.date(2026, 4, 7)))
        repo.insert(_make_krank_entry(datetime.date(2026, 4, 8)))

        results = repo.get_range(datetime.date(2026, 4, 8), datetime.date(2026, 4, 8))
        assert len(results) == 1
        assert results[0].entry_type == EntryType.krank

    def test_get_range_empty_returns_empty_list(self, db_conn):
        """get_range with no entries in range returns empty list."""
        repo = EntryRepository(db_conn)
        results = repo.get_range(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        assert results == []


class TestMigrate:
    """Tests for db.migrate() idempotency."""

    def test_migrate_idempotent(self, db_conn):
        """Calling migrate() twice does not raise or error."""
        migrate(db_conn)
        migrate(db_conn)  # Second call should be a no-op
