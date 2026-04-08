"""
CLI smoke tests for zeiterfassung using Typer's CliRunner.

Tests command exit codes and output fragments. Does not test full end-to-end
flow (CON-003 — no E2E tests at MVP). Uses in-memory approach via config mocking.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from zeiterfassung.cli.app import app

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
        for cmd in ["add", "edit", "delete", "bulk", "saldo", "show", "list", "fill-missing", "export", "config"]:
            assert cmd in result.output, f"Command '{cmd}' missing from --help output"

    def test_add_help_exits_zero(self):
        """zeit add --help exits with code 0."""
        result = runner.invoke(app, ["add", "--help"])
        assert result.exit_code == 0

    def test_edit_help_exits_zero(self):
        """zeit edit --help exits with code 0 (MVP B6)."""
        result = runner.invoke(app, ["edit", "--help"])
        assert result.exit_code == 0


class TestSaldoCommand:
    """Tests for the saldo command."""

    def test_saldo_empty_db_exits_zero(self, tmp_path):
        """
        zeit saldo with empty DB exits 0 and output contains '0:00' (TASK-035).
        Uses a temporary DB file path via mock.
        """
        db_path = tmp_path / "test.db"

        with patch("zeiterfassung.cli.app.get_db_path", return_value=db_path), \
             patch("zeiterfassung.cli.app.load_settings") as mock_settings:
            from zeiterfassung.config import Settings
            mock_settings.return_value = Settings(weekly_hours=40.0, bundesland="BY")
            result = runner.invoke(app, ["saldo"])

        assert result.exit_code == 0
        assert "0:00" in result.output


class TestAddCommand:
    """Tests for the add command."""

    def test_add_krank_exits_zero(self, tmp_path):
        """
        zeit add 2026-04-14 krank exits 0 with pre-seeded config (TASK-035).
        """
        db_path = tmp_path / "test.db"

        with patch("zeiterfassung.cli.app.get_db_path", return_value=db_path), \
             patch("zeiterfassung.cli.app.load_settings") as mock_settings:
            from zeiterfassung.config import Settings
            mock_settings.return_value = Settings(weekly_hours=40.0, bundesland="BY")
            result = runner.invoke(app, ["add", "2026-04-14", "krank"])

        assert result.exit_code == 0

    def test_add_invalid_date_exits_nonzero(self, tmp_path):
        """zeit add with invalid date format exits non-zero."""
        db_path = tmp_path / "test.db"
        with patch("zeiterfassung.cli.app.get_db_path", return_value=db_path), \
             patch("zeiterfassung.cli.app.load_settings") as mock_settings:
            from zeiterfassung.config import Settings
            mock_settings.return_value = Settings(weekly_hours=40.0, bundesland="BY")
            result = runner.invoke(app, ["add", "not-a-date", "krank"])
        assert result.exit_code != 0


class TestShowCommand:
    """Tests for the show command."""

    def test_show_exits_zero(self, tmp_path):
        """
        zeit show exits 0 and output contains column headers (TASK-035).
        """
        db_path = tmp_path / "test.db"

        with patch("zeiterfassung.cli.app.get_db_path", return_value=db_path), \
             patch("zeiterfassung.cli.app.load_settings") as mock_settings:
            from zeiterfassung.config import Settings
            mock_settings.return_value = Settings(weekly_hours=40.0, bundesland="BY")
            result = runner.invoke(app, ["show"])

        assert result.exit_code == 0
        # Check that at least one column header appears
        assert "Date" in result.output or "date" in result.output.lower()


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_valid_bundesland_exits_zero(self, tmp_path):
        """zeit config with valid bundesland exits 0."""
        with patch("zeiterfassung.config.save_settings"):
            result = runner.invoke(
                app, ["config", "--weekly-hours", "40.0", "--bundesland", "BY"]
            )
        assert result.exit_code == 0

    def test_config_invalid_bundesland_exits_one(self):
        """zeit config with invalid bundesland exits 1 with error message."""
        result = runner.invoke(
            app, ["config", "--weekly-hours", "40.0", "--bundesland", "INVALID"]
        )
        assert result.exit_code == 1

    def test_config_negative_hours_exits_one(self):
        """zeit config with negative hours exits 1."""
        result = runner.invoke(
            app, ["config", "--weekly-hours", "-1.0", "--bundesland", "BY"]
        )
        assert result.exit_code == 1
