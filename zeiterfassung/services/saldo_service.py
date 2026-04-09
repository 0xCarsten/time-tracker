"""
Balance (overtime balance) computation service.

Computes cumulative signed delta across all entries and missing workdays.
NEW-MIN-002: calls is_workday() from domain/rules.py directly for missing-workday
iteration; does not depend on EntryService to avoid unplanned cross-service coupling.
"""

from __future__ import annotations

import datetime
from typing import Optional

from zeiterfassung.config import Settings
from zeiterfassung.domain.models import IncompleteEntryError
from zeiterfassung.domain.rules import calculate_delta, is_workday
from zeiterfassung.repository.entry_repo import EntryRepository


class BalanceService:
    """
    Computes the cumulative overtime balance over a date range.

    Missing workdays subtract settings.daily_target_minutes (documented assumption:
    uses current settings value, not historical snapshot for missing days).
    """

    def __init__(self, repo: EntryRepository, settings: Settings) -> None:
        """
        Initialise with repository and settings.

        Parameters:
            repo: Entry repository for reading persisted entries.
            settings: User settings for daily target and state.
        """
        self._repo = repo
        self._settings = settings

    def compute(
        self,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
    ) -> int:
        """
        Compute cumulative balance in minutes.

        For entries in range: sum calculate_delta(entry).
        For missing workdays: subtract settings.daily_target_minutes.
        Returns 0 on empty DB (never raises).

        Parameters:
            from_date: Optional start of range (inclusive). Defaults to min date in DB.
            to_date: Optional end of range (inclusive). Defaults to today.

        Returns:
            Total signed delta in integer minutes.
        """
        effective_to = to_date or datetime.date.today()

        # Determine available range
        if from_date is None:
            min_date = self._repo.get_min_date()
            if min_date is None:
                return 0  # Empty DB
            effective_from = min_date
        else:
            effective_from = from_date

        entries = self._repo.get_range(effective_from, effective_to)
        entry_dates = {e.date for e in entries}

        total = 0
        for e in entries:
            try:
                total += calculate_delta(e)
            except IncompleteEntryError:
                pass  # Incomplete entries contribute 0 to balance

        # Subtract daily_target for each missing workday in range (NEW-MIN-002:
        # call is_workday() from domain/rules.py directly, no EntryService dep).
        current = effective_from
        while current <= effective_to:
            if (
                is_workday(current, self._settings.state, self._settings.weekend_work)
                and current not in entry_dates
            ):
                total -= self._settings.daily_target_minutes
            current += datetime.timedelta(days=1)

        return total
