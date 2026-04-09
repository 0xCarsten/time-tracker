"""
CLI smoke tests for zeiterfassung using Typer's CliRunner.

Tests command exit codes and output fragments. Does not test full end-to-end
flow (CON-003 — no E2E tests at MVP). Uses in-memory approach via config mocking.
"""

from __future__ import annotations

import datetime

from unittest.mock import patch

from typer.testing import CliRunner

from zeiterfassung.cli.app import app
from zeiterfassung.config import Settings

runner = CliRunner()


class TestHelpCommands:
    """Tests for CLI help output."""

    def test_root_help_exits_zero(self):
        """zeit --help exits with code 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_root_help_lists_all_commands(self):
        """zeit --help output contains all expected subcommands (TASK-036)."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in [
            "add",
            "edit",
            "delete",
            "bulk",
            "balance",
            "show",
            "list",
            "fill-missing",
            "export",
            "config",
        ]:
            assert cmd in result.output, f"Command '{cmd}' missing from --help output"

    def test_add_help_exits_zero(self):
        """zeit add --help exits with code 0."""
        result = runner.invoke(app, ["add", "--help"])
        assert result.exit_code == 0

    def test_edit_help_exits_zero(self):
        """zeit edit --help exits with code 0 (MVP B6)."""
        result = runner.invoke(app, ["edit", "--help"])
        assert result.exit_code == 0


class TestBalanceCommand:
    """Tests for the balance command."""

    def test_balance_empty_db_exits_zero(self, tmp_path):
        """
        zeit balance with empty DB exits 0 and output contains '0:00' (TASK-035).
        Uses a temporary DB file path via mock.
        """
        db_path = tmp_path / "test.db"

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_settings,
        ):
            mock_settings.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(app, ["balance"])

        assert result.exit_code == 0
        assert "0:00" in result.output


class TestAddCommand:
    """Tests for the add command."""

    def test_add_sick_exits_zero(self, tmp_path):
        """
        zeit add 2026-04-14 sick exits 0 with pre-seeded config (TASK-035).
        """
        db_path = tmp_path / "test.db"

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_settings,
        ):
            mock_settings.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(app, ["add", "2026-04-14", "sick"])

        assert result.exit_code == 0

    def test_add_invalid_date_exits_nonzero(self, tmp_path):
        """zeit add with invalid date format exits non-zero."""
        db_path = tmp_path / "test.db"
        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_settings,
        ):
            mock_settings.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(app, ["add", "not-a-date", "sick"])
        assert result.exit_code != 0

    def test_add_today_uses_current_date(self, tmp_path):
        """zeit add today sick resolves 'today' to datetime.date.today()."""
        db_path = tmp_path / "test.db"
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_settings,
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_dt.date.today.return_value = fixed_today
            mock_dt.date.fromisoformat = datetime.date.fromisoformat
            mock_settings.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(app, ["add", "today", "sick"])

        assert result.exit_code == 0
        assert "2026-04-08" in result.output or "Added" in result.output


class TestShowCommand:
    """Tests for the show command."""

    def test_show_exits_zero(self, tmp_path):
        """
        zeit show exits 0 and output contains column headers (TASK-035).
        """
        db_path = tmp_path / "test.db"

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_settings,
        ):
            mock_settings.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(app, ["show"])

        assert result.exit_code == 0
        # Check that at least one column header appears
        assert "Date" in result.output or "date" in result.output.lower()


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_valid_state_exits_zero(self, tmp_path):
        """zeit config with valid state exits 0."""
        with (
            patch("zeiterfassung.cli.app.save_settings"),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
        ):
            mock_load.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(
                app, ["config", "--weekly-hours", "40.0", "--state", "BY"]
            )
        assert result.exit_code == 0

    def test_config_invalid_state_exits_one(self):
        """zeit config with invalid state exits 1 with error message."""
        result = runner.invoke(
            app, ["config", "--weekly-hours", "40.0", "--state", "INVALID"]
        )
        assert result.exit_code == 1

    def test_config_negative_hours_exits_one(self):
        """zeit config with negative hours exits 1."""
        result = runner.invoke(
            app, ["config", "--weekly-hours", "-1.0", "--state", "BY"]
        )
        assert result.exit_code == 1

    def test_config_timezone_valid_exits_zero(self, tmp_path):
        """zeit config --timezone Europe/London saves valid timezone (TEST-012)."""
        with (
            patch("zeiterfassung.cli.app.save_settings"),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
        ):
            mock_load.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(
                app,
                [
                    "config",
                    "--weekly-hours",
                    "40.0",
                    "--state",
                    "BY",
                    "--timezone",
                    "Europe/London",
                ],
            )
        assert result.exit_code == 0
        assert "Europe/London" in result.output

    def test_config_timezone_invalid_exits_one(self):
        """zeit config --timezone Invalid/Zone exits 1 with error and no save (TEST-013)."""
        with (
            patch("zeiterfassung.cli.app.save_settings") as mock_save,
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
        ):
            mock_load.return_value = Settings(weekly_hours=40.0, state="BY")
            result = runner.invoke(
                app,
                [
                    "config",
                    "--weekly-hours",
                    "40.0",
                    "--state",
                    "BY",
                    "--timezone",
                    "Invalid/Zone",
                ],
            )
        assert result.exit_code == 1
        assert "Invalid" in result.output or "timezone" in result.output.lower()
        mock_save.assert_not_called()


class TestStartCommand:
    """Tests for the start command (TEST-014)."""

    def test_start_records_current_time(self, tmp_path):
        """zeit start calls start_entry with today's date and current time (TEST-014)."""
        db_path = tmp_path / "test.db"
        fixed_time = datetime.time(9, 15)
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
            patch("zeiterfassung.cli.app._now_in_tz", return_value=fixed_time),
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_load.return_value = Settings(
                weekly_hours=40.0, state="BY", timezone="Europe/Berlin"
            )
            mock_dt.date.today.return_value = fixed_today
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 4, 8, 9, 15, 0)
            result = runner.invoke(app, ["start"])

        assert result.exit_code == 0
        assert "09:15" in result.output
        assert "Started" in result.output

    def test_start_custom_time(self, tmp_path):
        """zeit start 08:30 records the provided time instead of current time."""
        db_path = tmp_path / "test.db"
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_dt.date.today.return_value = fixed_today
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 4, 8, 9, 0, 0)
            mock_dt.time.fromisoformat.side_effect = datetime.time.fromisoformat
            result = runner.invoke(app, ["start", "08:30"])

        assert result.exit_code == 0
        assert "08:30" in result.output
        assert "Started" in result.output

    def test_start_invalid_time_format_exits_with_error(self, tmp_path):
        """zeit start with a bad time string exits non-zero."""
        result = runner.invoke(app, ["start", "not-a-time"])
        assert result.exit_code != 0

    def test_start_duplicate_exits_one(self, tmp_path):
        """zeit start on a day with existing entry exits 1 with error."""
        db_path = tmp_path / "test.db"
        fixed_time = datetime.time(9, 0)
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
            patch("zeiterfassung.cli.app._now_in_tz", return_value=fixed_time),
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_load.return_value = Settings(
                weekly_hours=40.0, state="BY", timezone="Europe/Berlin"
            )
            mock_dt.date.today.return_value = fixed_today
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 4, 8, 9, 0, 0)
            # First start succeeds
            runner.invoke(app, ["start"])
            # Second start fails
            result = runner.invoke(app, ["start"])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestStopCommand:
    """Tests for the stop command (TEST-015)."""

    def test_stop_records_end_time_and_prints_delta(self, tmp_path):
        """zeit stop calls stop_entry and prints delta on success (TEST-015)."""
        db_path = tmp_path / "test.db"
        start_time = datetime.time(9, 0)
        end_time = datetime.time(17, 0)
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_load.return_value = Settings(
                weekly_hours=40.0, state="BY", timezone="Europe/Berlin"
            )
            mock_dt.date.today.return_value = fixed_today
            mock_dt.datetime.now.side_effect = [
                datetime.datetime(2026, 4, 8, 9, 0, 0),  # for start_entry
                datetime.datetime(2026, 4, 8, 17, 0, 0),  # for stop_entry updated_at
            ]

            # Start first, then stop with _now_in_tz mocked
            with patch("zeiterfassung.cli.app._now_in_tz") as mock_now:
                mock_now.return_value = start_time
                runner.invoke(app, ["start"])
                mock_now.return_value = end_time
                result = runner.invoke(app, ["stop"])

        assert result.exit_code == 0
        assert "Stopped" in result.output
        assert "17:00" in result.output

    def test_stop_without_start_exits_one(self, tmp_path):
        """zeit stop with no open entry exits 1."""
        db_path = tmp_path / "test.db"
        fixed_today = datetime.date(2026, 4, 8)

        with (
            patch("zeiterfassung.cli.app.get_db_path", return_value=db_path),
            patch("zeiterfassung.cli.app.load_settings") as mock_load,
            patch(
                "zeiterfassung.cli.app._now_in_tz", return_value=datetime.time(17, 0)
            ),
            patch("zeiterfassung.cli.app.datetime") as mock_dt,
        ):
            mock_load.return_value = Settings(
                weekly_hours=40.0, state="BY", timezone="Europe/Berlin"
            )
            mock_dt.date.today.return_value = fixed_today
            result = runner.invoke(app, ["stop"])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestConfigSettingsRoundtrip:
    """Tests for timezone in load_settings/save_settings (TEST-016, TEST-017)."""

    def test_load_settings_default_timezone(self, tmp_path):
        """load_settings returns timezone='Europe/Berlin' when absent from config (TEST-016)."""
        from zeiterfassung.config import load_settings

        # Load from a nonexistent config → defaults
        with patch(
            "zeiterfassung.config._config_path",
            return_value=tmp_path / "nonexistent.toml",
        ):
            s = load_settings()
        assert s.timezone == "Europe/Berlin"

    def test_save_and_load_timezone_roundtrip(self, tmp_path):
        """save_settings writes timezone; load_settings reads it back (TEST-017)."""
        from zeiterfassung.config import load_settings, save_settings

        config_path = tmp_path / "config.toml"
        with patch("zeiterfassung.config._config_path", return_value=config_path):
            s = Settings(weekly_hours=40.0, state="BY", timezone="America/New_York")
            save_settings(s)
            loaded = load_settings()

        assert loaded.timezone == "America/New_York"
