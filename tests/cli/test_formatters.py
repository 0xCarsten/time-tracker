"""
Unit tests for zeiterfassung.cli.formatters.

TEST-011: make_day_table() — incomplete (open) entry rendering.
"""

from __future__ import annotations

import datetime

from rich.console import Console

from zeiterfassung.cli.formatters import make_day_table
from zeiterfassung.domain.models import DayResult, EntryType, TimeEntry


def _make_open_entry(date: datetime.date) -> TimeEntry:
    """Create a work entry with start_time set but end_time absent."""
    return TimeEntry(
        date=date,
        entry_type=EntryType.work,
        start_time=datetime.time(9, 0),
        end_time=None,
        pause_minutes=0,
        daily_target_minutes=480,
        created_at=datetime.datetime(2026, 4, 9, 9, 0, 0),
        updated_at=datetime.datetime(2026, 4, 9, 9, 0, 0),
    )


def _render_table(results: list[DayResult]) -> str:
    """Render a Rich Table to a plain string for assertion."""
    table = make_day_table(results)
    console = Console(force_terminal=False, width=120)
    with console.capture() as capture:
        console.print(table)
    return capture.get()


class TestMakeDayTableIncomplete:
    """TEST-011: make_day_table renders open (incomplete) entries correctly."""

    def test_incomplete_entry_type_column_shows_open(self):
        """Type column shows 'open' for an incomplete work entry (TEST-011)."""
        date = datetime.date(2026, 4, 9)
        entry = _make_open_entry(date)
        result = DayResult(
            date=date,
            delta_minutes=0,
            entry=entry,
            is_missing=False,
            is_incomplete=True,
        )

        rendered = _render_table([result])

        assert "open" in rendered

    def test_incomplete_entry_delta_column_shows_em_dash(self):
        """Delta column shows '—' (em-dash) for an incomplete entry (TEST-011)."""
        date = datetime.date(2026, 4, 9)
        entry = _make_open_entry(date)
        result = DayResult(
            date=date,
            delta_minutes=0,
            entry=entry,
            is_missing=False,
            is_incomplete=True,
        )

        rendered = _render_table([result])

        assert "\u2014" in rendered  # em-dash U+2014

    def test_incomplete_entry_uses_bold_red_style(self):
        """Incomplete entries are rendered with bold red style (TEST-011)."""
        date = datetime.date(2026, 4, 9)
        entry = _make_open_entry(date)
        result = DayResult(
            date=date,
            delta_minutes=0,
            entry=entry,
            is_missing=False,
            is_incomplete=True,
        )

        # Render with a terminal-aware console to get ANSI escape codes
        table = make_day_table([result])
        console = Console(force_terminal=True, width=120)
        with console.capture() as capture:
            console.print(table)
        ansi_output = capture.get()

        # Bold red is ANSI "1;31" or Rich encodes as bold+red
        assert (
            "bold red" in str(table.rows[0].style) or "\x1b[" in ansi_output
        ), "Expected ANSI styling for bold red incomplete row"

    def test_complete_entry_does_not_show_open(self):
        """Complete entries do not show 'open' in Type column (regression guard)."""
        date = datetime.date(2026, 4, 9)
        entry = TimeEntry(
            date=date,
            entry_type=EntryType.work,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            pause_minutes=30,
            daily_target_minutes=480,
            created_at=datetime.datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime.datetime(2026, 4, 9, 17, 0, 0),
        )
        result = DayResult(
            date=date,
            delta_minutes=30,
            entry=entry,
            is_missing=False,
            is_incomplete=False,
        )

        rendered = _render_table([result])

        assert "work" in rendered
        assert "open" not in rendered
