"""
Holiday detection wrapper for zeiterfassung.

Thin wrapper around the `holidays` library for German public holiday detection.
Domain layer is I/O-free — all validation raises ValueError, never prints (GUD-001).
"""

from __future__ import annotations

import datetime
from typing import Optional

import holidays


def _validate_bundesland(code: str) -> None:
    """
    Validate that `code` is a recognised German Bundesland subdivision code.

    Raises:
        ValueError: If the code is not a valid subdivision (CRIT-001 fix).
    """
    valid = sorted(holidays.Germany.subdivisions)
    if code not in valid:
        raise ValueError(
            f"Invalid bundesland '{code}'; must be one of {valid}"
        )


def get_holidays(year: int, bundesland: str) -> set[datetime.date]:
    """
    Return the set of public holiday dates for the given year and Bundesland.

    Parameters:
        year: The calendar year.
        bundesland: German state code (e.g. 'BY', 'BE').

    Returns:
        Set of public holiday dates.

    Raises:
        ValueError: If bundesland code is not valid.
    """
    _validate_bundesland(bundesland)
    return set(holidays.Germany(state=bundesland, years=year).keys())


def is_public_holiday(date: datetime.date, bundesland: str) -> Optional[str]:
    """
    Check if `date` is a public holiday in the given Bundesland.

    Parameters:
        date: The date to test.
        bundesland: German state code.

    Returns:
        The holiday name string if `date` is a public holiday, else None.

    Raises:
        ValueError: If bundesland code is not valid (GUD-001).
    """
    _validate_bundesland(bundesland)
    de_holidays = holidays.Germany(state=bundesland, years=date.year)
    return de_holidays.get(date)
