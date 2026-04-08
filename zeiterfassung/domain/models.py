"""
Domain models for zeiterfassung.

This module contains pure data structures and domain exceptions.
The domain layer is I/O-free: no typer, rich, sqlite3, or openpyxl imports.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EntryType(str, Enum):
    """Supported entry types for time tracking."""

    work = "work"
    sick = "sick"
    vacation = "vacation"
    holiday = "holiday"
    absent = "absent"


@dataclass
class TimeEntry:
    """
    Represents a single time-tracking entry for one calendar day.

    All durations (pause_minutes, daily_target_minutes) are stored as integer minutes.
    daily_target_minutes is snapshotted at insert time (REQ-004).
    note is str | None — None means absent, not empty string.
    """

    date: datetime.date
    entry_type: EntryType
    pause_minutes: int
    daily_target_minutes: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    id: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    note: Optional[str] = None


@dataclass
class DayResult:
    """
    Aggregated result for a single day used in display and export.

    delta_minutes is the signed difference from target for this day.
    is_missing is True when no entry exists for a workday.
    """

    date: datetime.date
    entry: Optional[TimeEntry]
    delta_minutes: int
    is_missing: bool


@dataclass
class MissingDay:
    """
    Domain-only sentinel for a workday with no logged entry.

    Never persisted to the database (CON-001, R8).
    Used only in reporting and display logic.
    """

    date: datetime.date
    daily_target_minutes: int


class DuplicateEntryError(Exception):
    """Raised when inserting an entry that conflicts with an existing one (UNIQUE constraint)."""
