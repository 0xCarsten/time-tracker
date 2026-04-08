"""
Shared pytest fixtures for zeiterfassung test suite.

db_conn: Provides an in-memory SQLite connection with full schema for all
repository and service tests (MAJ-004 fix — no per-file DB setup duplication).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zeiterfassung.repository.db import get_connection


@pytest.fixture
def db_conn():
    """
    Provide an in-memory SQLite connection with the zeiterfassung schema.

    Creates schema on connect, yields the connection, closes on teardown.
    All repository and service tests use this fixture (MAJ-004 fix).
    """
    conn = get_connection(Path(":memory:"))
    yield conn
    conn.close()
