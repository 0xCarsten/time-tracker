"""
Business rules for zeiterfassung.

Pure domain logic: delta calculation per entry type, workday detection,
time parsing helpers. Zero I/O (GUD-001).

Delta strategies (GUD-002): each EntryType maps to a callable to avoid if/elif chains.
parse_time_range (GUD-003): single centralised time-range parser.
is_workday (GUD-004): single source of truth for workday detection.
"""

from __future__ import annotations

import datetime
import re
from typing import Callable

from zeiterfassung.domain.holidays import is_public_holiday
from zeiterfassung.domain.models import EntryType, IncompleteEntryError, TimeEntry

# Pre-compiled HH:MM pattern for time-range validation (GUD-003)
_HM_RE = re.compile(r"^\d{2}:\d{2}$")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def parse_time_range(raw: str) -> tuple[datetime.time, datetime.time]:
    """
    Parse a time-range string of the form "HH:MM-HH:MM".

    Parameters:
        raw: String like "09:00-17:30".

    Returns:
        Tuple of (start_time, end_time) as datetime.time objects.

    Raises:
        ValueError: If the format is invalid.
    """
    raw = raw.strip()
    # Require exactly one "-" separator and HH:MM format (colon mandatory)
    if raw.count("-") != 1:
        raise ValueError(f"Invalid time range '{raw}': expected format HH:MM-HH:MM")
    left, right = raw.split("-", 1)
    if not _HM_RE.match(left.strip()) or not _HM_RE.match(right.strip()):
        raise ValueError(f"Invalid time range '{raw}': expected format HH:MM-HH:MM")
    try:
        start = datetime.time.fromisoformat(left.strip())
        end = datetime.time.fromisoformat(right.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid time range '{raw}': {exc}") from exc
    return start, end


def decimal_hours_to_minutes(hours: float) -> int:
    """
    Convert decimal hours to integer minutes.

    Parameters:
        hours: Decimal hours (e.g. 1.5 = 90 minutes).

    Returns:
        Integer minutes (floor, not rounded).

    Examples:
        >>> decimal_hours_to_minutes(1.5)
        90
        >>> decimal_hours_to_minutes(0.25)
        15
    """
    return int(hours * 60)


def _time_to_minutes(t: datetime.time) -> int:
    """Convert a time object to total minutes since midnight."""
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------------------
# Delta strategies (GUD-002) — no if/elif chains
# ---------------------------------------------------------------------------


def _work_delta(entry: TimeEntry) -> int:
    """
    Compute delta for a work entry.

    Handles overnight shifts (end < start) by adding 1440 minutes.
    Raises ValueError if effective work time is negative.
    """
    start_min = _time_to_minutes(entry.start_time)  # type: ignore[arg-type]
    end_min = _time_to_minutes(entry.end_time)  # type: ignore[arg-type]

    if end_min <= start_min:
        # Overnight shift
        end_min += 1440

    effective_minutes = end_min - start_min - entry.pause_minutes
    if effective_minutes < 0:
        raise ValueError(
            f"Effective work time is negative ({effective_minutes} min): "
            f"pause ({entry.pause_minutes} min) exceeds work duration."
        )
    return effective_minutes - entry.daily_target_minutes


def _zero_delta(_entry: TimeEntry) -> int:
    """Delta is zero for sick, vacation, holiday — no overtime adjustment."""
    return 0


def _negative_target_delta(entry: TimeEntry) -> int:
    """Delta is -daily_target for absent — a full day missed."""
    return -entry.daily_target_minutes


# Strategy mapping per EntryType (GUD-002)
_DELTA_STRATEGIES: dict[EntryType, Callable[[TimeEntry], int]] = {
    EntryType.work: _work_delta,
    EntryType.sick: _zero_delta,
    EntryType.vacation: _zero_delta,
    EntryType.holiday: _zero_delta,
    EntryType.absent: _negative_target_delta,
}


def calculate_delta(entry: TimeEntry) -> int:
    """
    Compute the signed delta in minutes for a given TimeEntry.

    Parameters:
        entry: A TimeEntry domain object.

    Returns:
        Signed integer minutes: positive = overtime, negative = undertime.

    Raises:
        IncompleteEntryError: If work entry is missing start_time or end_time.
        ValueError: If work entry has invalid time values.
    """
    if not entry.is_complete:
        raise IncompleteEntryError(
            f"Entry for {entry.date} is incomplete (missing start or end time)."
        )
    strategy = _DELTA_STRATEGIES[entry.entry_type]
    return strategy(entry)


# ---------------------------------------------------------------------------
# Workday detection (GUD-004)
# ---------------------------------------------------------------------------


def is_workday(date: datetime.date, state: str, allow_weekend: bool = False) -> bool:
    """
    Determine if `date` is a billable workday.

    Returns True iff:
    - The date is a weekday (Mon–Fri) OR allow_weekend is True, AND
    - The date is NOT a public holiday in the given state.

    A holiday falling on a weekend returns False (R7 — no compensatory day).

    Parameters:
        date: The date to test.
        state: German state code (e.g. 'BY').
        allow_weekend: If True, Saturday and Sunday are considered potential workdays.

    Returns:
        True if the date is a workday, False otherwise.

    Raises:
        ValueError: If state code is invalid.
    """
    if date.weekday() >= 5 and not allow_weekend:  # Saturday = 5, Sunday = 6
        return False
    return is_public_holiday(date, state) is None
