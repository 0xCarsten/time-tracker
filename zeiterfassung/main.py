"""
Entry point module for the zeiterfassung CLI.

Re-exports the Typer app from cli.app so the `zeit` script entry point resolves.
"""

from zeiterfassung.cli.app import app

__all__ = ["app"]
