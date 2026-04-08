"""
Settings management for zeiterfassung.

Settings are stored in a TOML file at ~/.config/zeiterfassung/config.toml.
No settings table in the DB (YAGNI-001).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomli_w


_CONFIG_PATH = Path("~/.config/zeiterfassung/config.toml")

_DEFAULTS: dict = {
    "weekly_hours": 40.0,
    "state": "BY",
    "weekend_work": False,
}


@dataclass
class Settings:
    """
    User configuration for weekly working hours and German state.

    weekly_hours: Contracted weekly hours (e.g. 40.0 for full-time).
    state: German state code for public holiday detection (e.g. 'BY').
    weekend_work: If True, Saturday and Sunday are treated as potential workdays.
    """

    weekly_hours: float
    state: str
    db_path: Optional[str] = None
    weekend_work: bool = False

    @property
    def daily_target_minutes(self) -> int:
        """
        Compute the daily target in integer minutes (REQ-003).

        Raises:
            ValueError: If weekly_hours is not positive.
        """
        if self.weekly_hours <= 0:
            raise ValueError(
                f"weekly_hours must be positive, got {self.weekly_hours}"
            )
        return int(self.weekly_hours / 5 * 60)


def _config_path() -> Path:
    """Return the resolved config file path."""
    return _CONFIG_PATH.expanduser()


def load_settings() -> Settings:
    """
    Load settings from config.toml; return defaults if file is missing.

    Returns:
        A populated Settings object.
    """
    path = _config_path()
    if not path.exists():
        return Settings(
            weekly_hours=_DEFAULTS["weekly_hours"],
            state=_DEFAULTS["state"],
        )
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Settings(
        weekly_hours=float(data.get("weekly_hours", _DEFAULTS["weekly_hours"])),
        state=str(data.get("state", _DEFAULTS["state"])),
        db_path=data.get("db_path") or None,
        weekend_work=bool(data.get("weekend_work", _DEFAULTS["weekend_work"])),
    )


def save_settings(s: Settings) -> None:
    """
    Persist settings to config.toml, creating parent directories if needed.

    Parameters:
        s: The Settings object to save.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "weekly_hours": s.weekly_hours,
        "state": s.state,
        "weekend_work": s.weekend_work,
    }
    if s.db_path:
        data["db_path"] = s.db_path
    with path.open("wb") as f:
        tomli_w.dump(data, f)
