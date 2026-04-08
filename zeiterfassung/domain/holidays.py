"""
Holiday detection wrapper for zeiterfassung.

Thin wrapper around the `holidays` library for German public holiday detection.
Domain layer is I/O-free — all validation raises ValueError, never prints (GUD-001).
"""

from __future__ import annotations

import datetime
from typing import Optional

import holidays


def _validate_state(code: str) -> None:
    """
    Validate that `code` is a recognised German state subdivision code.

    Raises:
        ValueError: If the code is not a valid subdivision (CRIT-001 fix).
    """
    valid = sorted(holidays.country_holidays("DE").subdivisions)
    if code not in valid:
        raise ValueError(f"Invalid state code '{code}'; must be one of {valid}")


def get_holidays(year: int, state: str) -> set[datetime.date]:
    """
    Return the set of public holiday dates for the given year and state.

    Parameters:
        year: The calendar year.
        state: German state code (e.g. 'BY', 'BE').

    Returns:
        Set of public holiday dates.

    Raises:
        ValueError: If state code is not valid.
    """
    _validate_state(state)
    return set(holidays.country_holidays("DE", subdiv=state, years=year).keys())


def is_public_holiday(date: datetime.date, state: str) -> Optional[str]:
    """
    Check if `date` is a public holiday in the given state.

    Parameters:
        date: The date to test.
        state: German state code.

    Returns:
        The holiday name string if `date` is a public holiday, else None.

    Raises:
        ValueError: If state code is not valid (GUD-001).
    """
    _validate_state(state)
    de_holidays = holidays.country_holidays("DE", subdiv=state, years=date.year)
    return de_holidays.get(date)
