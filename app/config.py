from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Load application configuration from environment variables; example: config = AppConfig.from_environment()."""

    enable_history: bool
    history_db_path: Path

    @staticmethod
    def from_environment() -> "AppConfig":
        """Read app configuration from environment variables; example: config = AppConfig.from_environment()."""

        enable_history: bool = parse_bool_env(os.getenv("ENABLE_HISTORY", "false"))
        default_db_path: Path = Path("storage/history.db")
        history_db_path_raw: str = os.getenv("HISTORY_DB_PATH", str(default_db_path))
        history_db_path: Path = Path(history_db_path_raw)

        return AppConfig(enable_history=enable_history, history_db_path=history_db_path)


def parse_bool_env(raw_value: str) -> bool:
    """Safely convert an environment string to bool; example: enabled = parse_bool_env('true')."""

    normalized_value: str = raw_value.strip().lower()
    return normalized_value in {"1", "true", "yes", "on"}
