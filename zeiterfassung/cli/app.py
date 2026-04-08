"""
Typer CLI application for zeiterfassung.

All commands are defined here. Service layer is wired via _get_services().
The CLI is the only layer permitted to perform I/O (print, input, Rich console).
Domain ValueError exceptions are caught here and displayed as Rich error messages.

Commands: config, add, edit, delete, bulk, balance, show, list, fill-missing, export.
"""

from __future__ import annotations

import contextlib
import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from zeiterfassung.cli.formatters import (
    format_date,
    format_minutes_as_hhmm,
    make_day_table,
    make_balance_panel,
)
from zeiterfassung.config import load_settings, save_settings, Settings
from zeiterfassung.domain.holidays import is_public_holiday
from zeiterfassung.domain.models import DuplicateEntryError, EntryType
from zeiterfassung.repository.db import get_connection, get_db_path
from zeiterfassung.repository.entry_repo import EntryRepository
from zeiterfassung.services.entry_service import EntryService
from zeiterfassung.services.export_service import ExportService
from zeiterfassung.services.saldo_service import BalanceService

app = typer.Typer(name="zeit", add_completion=True, help="zeiterfassung — time tracking CLI")
console = Console()
err_console = Console(stderr=True)

# Module-level state for the optional --db global override
_db_override: Path | None = None


@app.callback()
def _main(
    db: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Override DB file path (also: TIMETRACK_DB env var or db_path in config.toml).",
        show_default=False,
    ),
) -> None:
    """zeiterfassung — time tracking CLI"""
    global _db_override
    _db_override = db


@contextlib.contextmanager
def _get_services():
    """
    Context manager that yields (entry_service, saldo_service, export_service).

    Ensures the DB connection is always closed on exit (MIN-003 mitigation).
    """
    settings = load_settings()
    # Resolve DB path: CLI --db > ZEIT_DB env > config.toml db_path > default
    db_path_override = _db_override or (
        Path(settings.db_path) if settings.db_path else None
    )
    conn = get_connection(get_db_path(db_path_override))
    try:
        repo = EntryRepository(conn)
        entry_service = EntryService(repo, settings)
        balance_service = BalanceService(repo, settings)
        export_service = ExportService(entry_service)
        yield entry_service, balance_service, export_service
    finally:
        conn.close()


def _parse_date(date_str: str) -> datetime.date:
    """
    Parse a date string in YYYY-MM-DD format only (ALT-006).

    Raises:
        typer.BadParameter: If format is invalid.
    """
    try:
        return datetime.date.fromisoformat(date_str)
    except ValueError:
        raise typer.BadParameter(
            f"Date must be YYYY-MM-DD, got '{date_str}'"
        )


def _parse_optional_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Parse an optional date string, returning None if input is None."""
    return _parse_date(date_str) if date_str else None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def config(
    weekly_hours: float = typer.Option(..., help="Weekly contracted hours (e.g. 40.0)"),
    state: str = typer.Option(..., help="German state code (e.g. BY, BE, NW)"),
    db_path: Optional[str] = typer.Option(
        None,
        "--db-path",
        help="Persistent custom DB path (stored in config.toml). Use --db for a one-off override.",
        show_default=False,
    ),
    weekend_work: bool = typer.Option(
        False,
        "--weekend-work/--no-weekend-work",
        help="Count Saturdays and Sundays as potential workdays (default: off).",
    ),
) -> None:
    """Configure weekly hours, state, and optional custom DB path."""
    try:
        is_public_holiday(datetime.date.today(), state)
    except ValueError as exc:
        err_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    if weekly_hours <= 0:
        err_console.print("[bold red]Error:[/bold red] weekly_hours must be positive.")
        raise typer.Exit(code=1)

    s = Settings(weekly_hours=weekly_hours, state=state, db_path=db_path or None, weekend_work=weekend_work)
    save_settings(s)
    db_info = f"\nDB path:      {db_path}" if db_path else ""
    console.print(
        f"[green]Config saved:[/green] weekly_hours={weekly_hours}, state={state}, weekend_work={weekend_work}{db_info}\n"
        f"Daily target: {format_minutes_as_hhmm(s.daily_target_minutes, signed=False)}"
    )


@app.command()
def add(
    date_str: str = typer.Argument(help="Date as YYYY-MM-DD"),
    entry_type: EntryType = typer.Argument(help="Entry type: work|sick|vacation|holiday|absent"),
    time_range: Optional[str] = typer.Argument(
        default=None, help="Time range as HH:MM-HH:MM (required for work)"
    ),
    pause: Optional[float] = typer.Option(None, help="Pause in decimal hours (e.g. 0.5)"),
    note: Optional[str] = typer.Option(None, help="Optional note"),
) -> None:
    """Add a time entry for a given date."""
    date = _parse_date(date_str)

    with _get_services() as (entry_service, _, __):
        # Auto-detect holiday: if date is a holiday and type is not work,
        # override to holiday and set note (REQ-008).
        try:
            holiday_name = is_public_holiday(date, entry_service._settings.state)
        except ValueError as exc:
            err_console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)

        if holiday_name and entry_type != EntryType.work:
            console.print(
                f"[yellow]Auto-detected public holiday:[/yellow] {holiday_name}. "
                f"Setting type to holiday."
            )
            entry_type = EntryType.holiday
            note = note or holiday_name

        try:
            entry = entry_service.add_entry(
                date=date,
                entry_type=entry_type,
                time_range_raw=time_range,
                pause_decimal=pause,
                note=note,
            )
            console.print(
                f"[green]Added:[/green] {entry.entry_type.value} on {format_date(entry.date)}"
            )
        except DuplicateEntryError:
            overwrite = typer.confirm(
                f"An entry already exists for {date_str}. Overwrite?", default=False
            )
            if not overwrite:
                console.print("Aborted.")
                raise typer.Exit(code=0)
            try:
                entry = entry_service.overwrite_entry(
                    date=date,
                    entry_type=entry_type,
                    time_range_raw=time_range,
                    pause_decimal=pause,
                    note=note,
                )
                console.print(
                    f"[green]Updated:[/green] {entry.entry_type.value} on {format_date(entry.date)}"
                )
            except ValueError as exc:
                err_console.print(f"[bold red]Error:[/bold red] {exc}")
                raise typer.Exit(code=1)
        except ValueError as exc:
            err_console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command()
def edit(
    date_str: str = typer.Argument(help="Date as YYYY-MM-DD"),
    entry_type: Optional[EntryType] = typer.Option(None, "--type", help="New entry type"),
    time_range: Optional[str] = typer.Option(None, "--time", help="New time range HH:MM-HH:MM"),
    pause: Optional[float] = typer.Option(None, help="New pause in decimal hours"),
    note: Optional[str] = typer.Option(None, help="New note"),
) -> None:
    """Edit an existing time entry. Only provided fields are updated (MVP B6)."""
    date = _parse_date(date_str)

    with _get_services() as (entry_service, _, __):
        existing = entry_service.get_entry(date)
        if existing is None:
            err_console.print(f"[bold red]No entry found for {date_str}[/bold red]")
            raise typer.Exit(code=1)

        # NEW-MIN-001: use `if x is not None` not `x or existing.x` to preserve falsy values.
        merged_type = entry_type if entry_type is not None else existing.entry_type
        merged_pause = pause if pause is not None else (existing.pause_minutes / 60)

        # Build merged time range string from existing if not provided
        if time_range is not None:
            merged_time_range = time_range
        elif existing.start_time and existing.end_time:
            merged_time_range = (
                f"{existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')}"
            )
        else:
            merged_time_range = None

        merged_note = note if note is not None else existing.note

        try:
            updated = entry_service.overwrite_entry(
                date=date,
                entry_type=merged_type,
                time_range_raw=merged_time_range,
                pause_decimal=merged_pause,
                note=merged_note,
            )
            console.print(
                f"[green]Updated:[/green] {updated.entry_type.value} on {format_date(updated.date)}"
            )
        except ValueError as exc:
            err_console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command()
def delete(
    date_str: str = typer.Argument(help="Date as YYYY-MM-DD"),
) -> None:
    """Delete the entry for a given date."""
    date = _parse_date(date_str)
    typer.confirm(f"Delete entry for {date_str}?", abort=True)

    with _get_services() as (entry_service, _, __):
        deleted = entry_service.delete_entry(date)
        if deleted:
            console.print(f"[green]Deleted entry for {date_str}.[/green]")
        else:
            console.print(f"[yellow]No entry found for {date_str}.[/yellow]")


@app.command()
def bulk() -> None:
    """Interactive bulk entry mode. Enter one entry per line; empty line or 'done' to exit."""
    console.print(
        "[bold]Bulk entry mode[/bold] — format: YYYY-MM-DD HH:MM-HH:MM [pDECIMAL] "
        "or YYYY-MM-DD sick|vacation|absent|holiday [NOTE]\n"
        "Empty line or 'done' to exit."
    )

    count = 0
    with _get_services() as (entry_service, _, __):
        while True:
            line = Prompt.ask("[cyan]>[/cyan]", default="")
            if not line or line.strip().lower() == "done":
                break
            try:
                _process_bulk_line(line.strip(), entry_service)
                count += 1
                console.print(f"  [green]✓[/green] Entry #{count} added.")
            except Exception as exc:  # noqa: BLE001
                err_console.print(f"  [red]Error:[/red] {exc} — line skipped.")

    console.print(f"[green]Bulk entry complete.[/green] {count} entries added.")


def _process_bulk_line(line: str, entry_service: EntryService) -> None:
    """
    Parse and insert a single bulk entry line.

    Formats:
        YYYY-MM-DD HH:MM-HH:MM [pDECIMAL]
        YYYY-MM-DD sick|vacation|absent|holiday [NOTE...]
    """
    parts = line.split()
    if len(parts) < 2:
        raise ValueError(f"Invalid format: '{line}'")

    date = _parse_date(parts[0])
    second = parts[1]

    # Detect if second token is a time range
    if "-" in second and ":" in second:
        # Work entry
        time_range = second
        pause_decimal: Optional[float] = None
        if len(parts) > 2 and parts[2].startswith("p"):
            pause_decimal = float(parts[2][1:])
        entry_service.add_entry(
            date=date,
            entry_type=EntryType.work,
            time_range_raw=time_range,
            pause_decimal=pause_decimal,
        )
    else:
        entry_type = EntryType(second)
        note = " ".join(parts[2:]) if len(parts) > 2 else None
        entry_service.add_entry(
            date=date,
            entry_type=entry_type,
            note=note,
        )


@app.command()
def balance(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Show cumulative overtime balance."""
    from_d = _parse_optional_date(from_date)
    to_d = _parse_optional_date(to_date)

    with _get_services() as (_, balance_service, __):
        total = balance_service.compute(from_date=from_d, to_date=to_d)

    console.print(make_balance_panel(total))


@app.command()
def show(
    week: Optional[int] = typer.Option(None, help="ISO week number (default: current week)"),
    month: Optional[int] = typer.Option(None, help="Month number 1-12"),
) -> None:
    """Show entries for current week (or specified week/month)."""
    today = datetime.date.today()

    if month is not None:
        year = today.year
        from_d = datetime.date(year, month, 1)
        # Last day of month
        if month == 12:
            to_d = datetime.date(year, 12, 31)
        else:
            to_d = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    else:
        target_week = week if week is not None else today.isocalendar()[1]
        year = today.year
        # Find Monday of target_week
        jan4 = datetime.date(year, 1, 4)
        start_of_week1 = jan4 - datetime.timedelta(days=jan4.weekday())
        from_d = start_of_week1 + datetime.timedelta(weeks=target_week - 1)
        to_d = from_d + datetime.timedelta(days=6)

    # Never show future days as missing — cap to today unless week/month was
    # explicitly specified (in that case the user wants the full week).
    if week is None and month is None:
        to_d = min(to_d, today)
    elif month is not None:
        to_d = min(to_d, today)

    with _get_services() as (entry_service, _, __):
        results = entry_service.build_day_results(from_d, to_d)

    console.print(make_day_table(results))


@app.command(name="list")
def list_entries(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """List all entries in a date range."""
    today = datetime.date.today()
    from_d = _parse_optional_date(from_date) or datetime.date(today.year, today.month, 1)
    to_d = _parse_optional_date(to_date) or today

    with _get_services() as (entry_service, _, __):
        results = entry_service.build_day_results(from_d, to_d)

    console.print(make_day_table(results))


@app.command()
def fill_missing(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Interactively fill missing workdays. Press Enter to skip any date."""
    today = datetime.date.today()
    from_d = _parse_optional_date(from_date) or datetime.date(today.year, today.month, 1)
    to_d = _parse_optional_date(to_date) or today

    with _get_services() as (entry_service, _, __):
        missing = entry_service.get_missing_workdays(from_d, to_d)

        if not missing:
            console.print("[green]No missing workdays in range.[/green]")
            return

        console.print(f"[yellow]{len(missing)} missing workday(s) found.[/yellow]")
        for date in missing:
            console.print(f"\n[cyan]{format_date(date)}[/cyan]")
            type_str = Prompt.ask(
                "  Entry type (work/sick/vacation/absent/holiday) or Enter to skip",
                default="",
            )
            if not type_str:
                continue
            try:
                et = EntryType(type_str.lower())
            except ValueError:
                console.print(f"  [red]Unknown type '{type_str}', skipping.[/red]")
                continue

            time_range = None
            pause = None
            if et == EntryType.work:
                time_range = Prompt.ask("  Time range (HH:MM-HH:MM)", default="")
                if not time_range:
                    console.print("  [red]Time range required for work, skipping.[/red]")
                    continue
                pause_str = Prompt.ask("  Pause in decimal hours (Enter for 0)", default="0")
                try:
                    pause = float(pause_str)
                except ValueError:
                    pause = 0.0

            try:
                entry_service.add_entry(
                    date=date, entry_type=et, time_range_raw=time_range, pause_decimal=pause
                )
                console.print(f"  [green]Added {et.value}.[/green]")
            except Exception as exc:  # noqa: BLE001
                err_console.print(f"  [red]Error:[/red] {exc}")


@app.command()
def export(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
    output: Optional[Path] = typer.Option(None, help="Output .xlsx filename"),
) -> None:
    """Export time entries to Excel (.xlsx)."""
    today = datetime.date.today()
    from_d = _parse_optional_date(from_date) or datetime.date(today.year, 1, 1)
    to_d = _parse_optional_date(to_date) or today
    out_path = output or Path(f"zeit-export-{today:%Y%m%d}.xlsx")

    with _get_services() as (_, __, export_service):
        resolved = export_service.export_excel(from_d, to_d, out_path)

    console.print(f"[green]Exported to:[/green] {resolved}")
