"""
CRUD repository for TimeEntry records.

Maps between SQLite rows and TimeEntry domain objects (PAT-002).
db.py is responsible for connection management; this module is responsible for
query logic and object mapping only.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Optional

from zeiterfassung.domain.models import DuplicateEntryError, EntryType, TimeEntry


class EntryRepository:
    """
    Repository for CRUD operations on the entries table.

    All methods accept and return domain objects (TimeEntry).
    Mapping from raw sqlite3.Row to TimeEntry is done by _row_to_entry.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Initialise with an open SQLite connection.

        Parameters:
            conn: An open sqlite3.Connection (row_factory must be sqlite3.Row).
        """
        self._conn = conn

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> TimeEntry:
        """
        Map a sqlite3.Row from the entries table to a TimeEntry domain object.

        note is mapped as str | None — never coerced to empty string (MIN-002).
        """
        return TimeEntry(
            id=row["id"],
            date=datetime.date.fromisoformat(row["date"]),
            entry_type=EntryType(row["entry_type"]),
            start_time=(
                datetime.time.fromisoformat(row["start_time"])
                if row["start_time"]
                else None
            ),
            end_time=(
                datetime.time.fromisoformat(row["end_time"])
                if row["end_time"]
                else None
            ),
            pause_minutes=int(row["pause_minutes"]),
            daily_target_minutes=int(row["daily_target_minutes"]),
            note=row["note"],  # None if NULL in DB
            created_at=datetime.datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.datetime.fromisoformat(row["updated_at"]),
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert(self, entry: TimeEntry) -> TimeEntry:
        """
        Insert a new TimeEntry and return it with the generated id.

        Parameters:
            entry: TimeEntry to persist.

        Returns:
            The same entry with its database-assigned id.

        Raises:
            DuplicateEntryError: If a UNIQUE(date, entry_type) conflict exists.
        """
        try:
            cur = self._conn.execute(
                """
                INSERT INTO entries
                    (date, entry_type, start_time, end_time, pause_minutes,
                     daily_target_minutes, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.date.isoformat(),
                    entry.entry_type.value,
                    entry.start_time.strftime("%H:%M") if entry.start_time else None,
                    entry.end_time.strftime("%H:%M") if entry.end_time else None,
                    entry.pause_minutes,
                    entry.daily_target_minutes,
                    entry.note,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateEntryError(
                f"Entry already exists for {entry.date} / {entry.entry_type.value}"
            ) from exc
        entry.id = cur.lastrowid
        return entry

    def upsert(self, entry: TimeEntry) -> TimeEntry:
        """
        Insert or replace an entry (INSERT OR REPLACE).

        This is the ONLY method that may overwrite an existing entry.
        Called exclusively by EntryService.overwrite_entry (CRIT-002 / PAT-001).

        Parameters:
            entry: TimeEntry to persist.

        Returns:
            The entry with its id (newly generated if replaced).
        """
        now = datetime.datetime.now().isoformat()
        # Delete any existing entry for this date regardless of type,
        # so a type change (e.g. krank -> urlaub) replaces the old row.
        self._conn.execute(
            "DELETE FROM entries WHERE date = ?",
            (entry.date.isoformat(),),
        )
        cur = self._conn.execute(
            """
            INSERT INTO entries
                (date, entry_type, start_time, end_time, pause_minutes,
                 daily_target_minutes, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.date.isoformat(),
                entry.entry_type.value,
                entry.start_time.strftime("%H:%M") if entry.start_time else None,
                entry.end_time.strftime("%H:%M") if entry.end_time else None,
                entry.pause_minutes,
                entry.daily_target_minutes,
                entry.note,
                entry.created_at.isoformat(),
                now,
            ),
        )
        self._conn.commit()
        entry.id = cur.lastrowid
        return entry

    def delete_by_date(self, date: datetime.date) -> bool:
        """
        Delete the entry for the given date.

        Parameters:
            date: The date whose entry to delete.

        Returns:
            True if a row was deleted, False if no entry existed.
        """
        cur = self._conn.execute(
            "DELETE FROM entries WHERE date = ?", (date.isoformat(),)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_by_date(self, date: datetime.date) -> Optional[TimeEntry]:
        """
        Retrieve the entry for a specific date, or None if not found.

        Parameters:
            date: The date to look up.

        Returns:
            TimeEntry if found, None otherwise.
        """
        row = self._conn.execute(
            "SELECT * FROM entries WHERE date = ?", (date.isoformat(),)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_range(
        self, from_date: datetime.date, to_date: datetime.date
    ) -> list[TimeEntry]:
        """
        Retrieve all entries in the inclusive date range [from_date, to_date].

        Parameters:
            from_date: Start date (inclusive).
            to_date: End date (inclusive).

        Returns:
            List of TimeEntry objects sorted by date ascending.
        """
        rows = self._conn.execute(
            "SELECT * FROM entries WHERE date BETWEEN ? AND ? ORDER BY date ASC",
            (from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_min_date(self) -> datetime.date | None:
        """
        Return the earliest date stored in the entries table, or None if empty.

        Returns:
            The minimum date as a datetime.date, or None for an empty database.
        """
        row = self._conn.execute("SELECT MIN(date) AS min_date FROM entries").fetchone()
        min_str = row["min_date"] if row else None
        return datetime.date.fromisoformat(min_str) if min_str else None
