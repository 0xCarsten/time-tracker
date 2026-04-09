"""
Entry service for zeiterfassung.

Orchestrates use cases for creating, editing, deleting, and querying entries.
All input parsing happens at the service boundary; domain objects are passed down.
CLI must never call repo.* directly (PAT-001).
"""

from __future__ import annotations

import datetime
from typing import Optional

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import (
    DayResult,
    DuplicateEntryError,
    EntryType,
    IncompleteEntryError,
    TimeEntry,
)
from zeiterfassung.domain.rules import (
    calculate_delta,
    decimal_hours_to_minutes,
    is_workday,
    parse_time_range,
)
from zeiterfassung.repository.entry_repo import EntryRepository


class EntryService:
    """
    Application service for time entry management.

    Coordinates domain logic with the EntryRepository.
    All overwrite operations must go through overwrite_entry (CRIT-002).
    """

    def __init__(self, repo: EntryRepository, settings: Settings) -> None:
        """
        Initialise with repository and settings.

        Parameters:
            repo: Persistent storage for entries.
            settings: User configuration (weekly_hours, state).
        """
        self._repo = repo
        self._settings = settings

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_entry(
        self,
        date: datetime.date,
        entry_type: EntryType,
        time_range_raw: Optional[str] = None,
        pause_decimal: Optional[float] = None,
        note: Optional[str] = None,
    ) -> TimeEntry:
        """
        Parse inputs, snapshot daily_target_minutes, and insert a new entry.

        Parameters:
            date: The date for this entry.
            entry_type: Type of entry (work, sick, etc.).
            time_range_raw: Optional "HH:MM-HH:MM" string (required for work).
            pause_decimal: Optional pause in decimal hours (e.g. 0.5 = 30 min).
            note: Optional note string.

        Returns:
            The persisted TimeEntry with database-assigned id.

        Raises:
            ValueError: If time_range_raw is malformed or time arithmetic fails.
            DuplicateEntryError: If an entry already exists for this date.
        """
        start_time, end_time = self._parse_times(time_range_raw)
        pause_minutes = (
            decimal_hours_to_minutes(pause_decimal) if pause_decimal is not None else 0
        )
        now = datetime.datetime.now()
        entry = TimeEntry(
            date=date,
            entry_type=entry_type,
            start_time=start_time,
            end_time=end_time,
            pause_minutes=pause_minutes,
            daily_target_minutes=self._settings.daily_target_minutes,
            note=note,
            created_at=now,
            updated_at=now,
        )
        return self._repo.insert(entry)

    def overwrite_entry(
        self,
        date: datetime.date,
        entry_type: EntryType,
        time_range_raw: Optional[str] = None,
        pause_decimal: Optional[float] = None,
        note: Optional[str] = None,
    ) -> TimeEntry:
        """
        Parse inputs, snapshot daily_target_minutes, and upsert (overwrite) an entry.

        This is the SOLE repository path for any overwrite operation.
        CLI must not call repo.upsert directly (PAT-001 / CRIT-002).

        Parameters:
            date: The date for this entry.
            entry_type: Type of entry.
            time_range_raw: Optional "HH:MM-HH:MM" string.
            pause_decimal: Optional pause in decimal hours.
            note: Optional note string.

        Returns:
            The persisted (upserted) TimeEntry.
        """
        existing = self._repo.get_by_date(date)
        start_time, end_time = self._parse_times(time_range_raw)
        pause_minutes = (
            decimal_hours_to_minutes(pause_decimal) if pause_decimal is not None else 0
        )
        now = datetime.datetime.now()
        # Preserve the original created_at timestamp if the entry already exists
        created_at = existing.created_at if existing is not None else now
        entry = TimeEntry(
            date=date,
            entry_type=entry_type,
            start_time=start_time,
            end_time=end_time,
            pause_minutes=pause_minutes,
            daily_target_minutes=self._settings.daily_target_minutes,
            note=note,
            created_at=created_at,
            updated_at=now,
        )
        return self._repo.upsert(entry)

    def delete_entry(self, date: datetime.date) -> bool:
        """
        Delete the entry for the given date.

        Parameters:
            date: The date whose entry to remove.

        Returns:
            True if deleted, False if not found.
        """
        return self._repo.delete_by_date(date)

    def start_entry(self, date: datetime.date, start_time: datetime.time) -> TimeEntry:
        """
        Record start_time for today's work entry.

        Creates a new work entry with start_time set and end_time=None.

        Parameters:
            date: The date to record (typically today).
            start_time: The wall-clock start time (naive, already timezone-resolved by CLI).

        Returns:
            The persisted TimeEntry.

        Raises:
            DuplicateEntryError: If any entry already exists for this date.
        """
        existing = self._repo.get_by_date(date)
        if existing is not None:
            raise DuplicateEntryError(
                f"An entry already exists for {date}. Use 'zeit edit' or 'zeit delete' to modify it."
            )
        now = datetime.datetime.now()
        entry = TimeEntry(
            date=date,
            entry_type=EntryType.work,
            start_time=start_time,
            end_time=None,
            pause_minutes=0,
            daily_target_minutes=self._settings.daily_target_minutes,
            created_at=now,
            updated_at=now,
        )
        return self._repo.insert(entry)

    def stop_entry(
        self,
        date: datetime.date,
        end_time: datetime.time,
        pause_decimal: Optional[float] = None,
    ) -> TimeEntry:
        """
        Record end_time for an open work entry.

        Parameters:
            date: The date of the open entry (typically today).
            end_time: The wall-clock end time (naive, already timezone-resolved by CLI).
            pause_decimal: Optional pause in decimal hours (e.g. 0.5 = 30 min).

        Returns:
            The updated, persisted TimeEntry.

        Raises:
            ValueError: If no open work entry exists, if entry is already complete,
                        if entry type is not work, or if effective minutes are non-positive.
        """
        existing = self._repo.get_by_date(date)
        if (
            existing is None
            or existing.entry_type != EntryType.work
            or existing.start_time is None
        ):
            raise ValueError(f"No open work entry for {date}. Run 'zeit start' first.")
        if existing.end_time is not None:
            raise ValueError(
                f"Entry for {date} is already complete. Use 'zeit edit' to change it."
            )
        pause_minutes = (
            int(pause_decimal * 60)
            if pause_decimal is not None
            else existing.pause_minutes
        )
        # Note: _time_to_minutes() exists in domain/rules.py but is intentionally private.
        # This inline arithmetic is a deliberate duplicate kept here so the service layer
        # avoids importing implementation-detail helpers from the domain rules module.
        start_minutes = existing.start_time.hour * 60 + existing.start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        effective_minutes = end_minutes - start_minutes - pause_minutes
        if effective_minutes <= 0:
            raise ValueError(
                "End time is before start time or pause exceeds elapsed time. "
                "For overnight entries, use 'zeit edit'."
            )
        existing.end_time = end_time
        existing.pause_minutes = pause_minutes
        existing.updated_at = datetime.datetime.now()
        return self._repo.upsert(existing)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_entry(self, date: datetime.date) -> Optional[TimeEntry]:
        """
        Retrieve the entry for a specific date.

        Parameters:
            date: The date to look up.

        Returns:
            TimeEntry if found, else None.
        """
        return self._repo.get_by_date(date)

    def get_missing_workdays(
        self, from_date: datetime.date, to_date: datetime.date
    ) -> list[datetime.date]:
        """
        Return a list of workdays in [from_date, to_date] with no entry.

        Weekends and public holidays are excluded (GUD-004).

        Parameters:
            from_date: Start of range (inclusive).
            to_date: End of range (inclusive).

        Returns:
            Sorted list of missing workday dates.
        """
        entries = self._repo.get_range(from_date, to_date)
        entry_dates = {e.date for e in entries}
        missing = []
        current = from_date
        while current <= to_date:
            if is_workday(current, self._settings.state) and current not in entry_dates:
                missing.append(current)
            current += datetime.timedelta(days=1)
        return missing

    def build_day_results(
        self, from_date: datetime.date, to_date: datetime.date
    ) -> list[DayResult]:
        """
        Build a sorted list of DayResult objects for the given date range.

        Each workday is represented: entries get their calculated delta,
        missing workdays get is_missing=True and delta = -daily_target_minutes.
        Running balance accumulates across results in date order.

        Parameters:
            from_date: Start of range (inclusive).
            to_date: End of range (inclusive).

        Returns:
            List of DayResult sorted by date ascending with running balance.
        """
        entries = self._repo.get_range(from_date, to_date)
        entry_map = {e.date: e for e in entries}

        # A day is only "missing" if it falls within the active tracking window:
        # [first_entry_date, today].  This prevents deleted entries and future
        # workdays from appearing as gaps in the output.
        today = datetime.date.today()
        min_date = self._repo.get_min_date()

        results: list[DayResult] = []
        current = from_date
        target = self._settings.daily_target_minutes

        while current <= to_date:
            if current in entry_map:
                entry = entry_map[current]
                try:
                    delta = calculate_delta(entry)
                    is_incomplete = False
                except IncompleteEntryError:
                    delta = 0
                    is_incomplete = True
                results.append(
                    DayResult(
                        date=current,
                        entry=entry,
                        delta_minutes=delta,
                        is_missing=False,
                        is_incomplete=is_incomplete,
                    )
                )
            elif (
                is_workday(current, self._settings.state, self._settings.weekend_work)
                and min_date is not None
                and min_date <= current <= today
            ):
                results.append(
                    DayResult(
                        date=current, entry=None, delta_minutes=-target, is_missing=True
                    )
                )
            current += datetime.timedelta(days=1)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_times(
        self, time_range_raw: Optional[str]
    ) -> tuple[Optional[datetime.time], Optional[datetime.time]]:
        """Parse an optional time range string into start and end times."""
        if time_range_raw is None:
            return None, None
        start, end = parse_time_range(time_range_raw)
        return start, end
