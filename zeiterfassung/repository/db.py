"""
Database connection management and schema versioning for zeiterfassung.

Uses PRAGMA user_version for schema versioning (REQ-014).
Creates the DB directory and schema on first connect.
migrate() applies sequential ALTER TABLE statements idempotently.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_db_path(override: Path | None = None) -> Path:
    """
    Return the DB file path, creating its parent directory if needed.

    Resolution order:
      1. ``override`` argument (CLI ``--db`` flag)
      2. ``TIMETRACK_DB`` environment variable
      3. Default: ``~/.zeiterfassung/zeit.db``

    Parameters:
        override: Explicit path supplied by the caller (highest priority).

    Returns:
        Resolved Path to the SQLite file (SEC-002: expanduser applied).
    """
    import os

    if override is not None:
        path = override.expanduser().resolve()
    elif env := os.environ.get("TIMETRACK_DB"):
        path = Path(env).expanduser().resolve()
    else:
        path = Path.home() / ".zeiterfassung" / "zeit.db"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Open an SQLite connection, configure settings, and ensure schema is up-to-date.

    On first connect (user_version == 0), creates the full schema.
    Always runs migrate() to apply any pending schema changes.

    Parameters:
        db_path: Path to the SQLite database file (use Path(':memory:') for tests).

    Returns:
        An open sqlite3.Connection with row_factory set.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        create_schema(conn)

    migrate(conn)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create the initial database schema (version 1).

    No settings table — config is stored in ~/.config/zeiterfassung/config.toml
    (YAGNI-001, MAJ-001 fix). Only the entries table is created.

    Parameters:
        conn: An open SQLite connection.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            date                 TEXT    NOT NULL,
            entry_type           TEXT    NOT NULL,
            start_time           TEXT,
            end_time             TEXT,
            pause_minutes        INTEGER NOT NULL DEFAULT 0,
            daily_target_minutes INTEGER NOT NULL,
            note                 TEXT,
            created_at           TEXT    NOT NULL,
            updated_at           TEXT    NOT NULL,
            UNIQUE(date, entry_type)
        );
        PRAGMA user_version = 1;
    """
    )
    conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    """
    Apply any pending migrations based on PRAGMA user_version.

    Each migration block increments user_version by one.
    Idempotent: skips already-applied migrations.

    Parameters:
        conn: An open SQLite connection.
    """
    # No pending schema migrations at version 1.
