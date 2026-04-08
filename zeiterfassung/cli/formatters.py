"""
Rich output formatters for zeiterfassung CLI.

All I/O and presentation logic lives here in the CLI layer.
Domain and service layers must never call these functions.
"""

from __future__ import annotations

import datetime

from rich.panel import Panel
from rich.table import Table

from zeiterfassung.domain.models import DayResult


def format_minutes_as_hhmm(minutes: int, signed: bool = True) -> str:
    """
    Format a signed integer minute value as HH:MM string.

    Parameters:
        minutes: Signed integer minutes (positive = overtime, negative = deficit).
        signed: If True, prepend '+' for positive values.

    Returns:
        Formatted string like "+01:30" or "-00:45" or "08:00".
    """
    sign = ""
    if signed:
        sign = "+" if minutes >= 0 else "-"
    abs_min = abs(minutes)
    hours, mins = divmod(abs_min, 60)
    return f"{sign}{hours:02d}:{mins:02d}"


def format_date(d: datetime.date) -> str:
    """
    Format a date as YYYY-MM-DD.

    Parameters:
        d: The date to format.

    Returns:
        ISO-8601 date string.
    """
    return d.strftime("%Y-%m-%d")


def make_day_table(results: list[DayResult]) -> Table:
    """
    Build a Rich Table showing daily time entries with running saldo.

    Missing workdays are styled bold red.
    Columns: Date, Type, Start, End, Pause, Delta, Running Saldo.

    Parameters:
        results: List of DayResult objects from EntryService.build_day_results.

    Returns:
        A Rich Table ready to print.
    """
    table = Table(title="Zeiterfassung", show_header=True, header_style="bold blue")
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Type", width=10)
    table.add_column("Start", width=6)
    table.add_column("End", width=6)
    table.add_column("Pause", width=6)
    table.add_column("Delta", width=8)
    table.add_column("Running Saldo", width=14)

    running = 0
    for result in results:
        running += result.delta_minutes
        style = "bold red" if result.is_missing else ""
        entry = result.entry

        if entry:
            row_type = entry.entry_type.value
            start = entry.start_time.strftime("%H:%M") if entry.start_time else ""
            end = entry.end_time.strftime("%H:%M") if entry.end_time else ""
            pause = format_minutes_as_hhmm(entry.pause_minutes, signed=False)
        else:
            row_type = "missing"
            start = ""
            end = ""
            pause = ""

        table.add_row(
            format_date(result.date),
            row_type,
            start,
            end,
            pause,
            format_minutes_as_hhmm(result.delta_minutes),
            format_minutes_as_hhmm(running),
            style=style,
        )

    return table


def make_saldo_panel(minutes: int) -> Panel:
    """
    Build a Rich Panel showing the cumulative overtime balance.

    Parameters:
        minutes: Signed integer minutes of total saldo.

    Returns:
        A Rich Panel with the saldo formatted as HH:MM.
    """
    formatted = format_minutes_as_hhmm(minutes)
    color = "green" if minutes >= 0 else "red"
    return Panel(
        f"[{color}]{formatted}[/{color}]",
        title="Saldo (Overtime Balance)",
        expand=False,
    )
