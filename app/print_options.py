"""Admin settings for the printout."""

import sqlite3

from app import config, db

CREDIT_KEY = "print_credit"


def credit_enabled(conn: sqlite3.Connection) -> bool:
    """Show "Wegweiser (github.com/...)" in the sources line of the printout (default: yes)."""
    return db.setting_get(conn, CREDIT_KEY) != "0"


def set_credit(conn: sqlite3.Connection, enabled: bool) -> None:
    db.setting_put(conn, CREDIT_KEY, "1" if enabled else "0")


def credit_text() -> str:
    """Project name and address without words, so it needs no translation."""
    address = config.PROJECT_URL.removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"{config.APP_NAME} ({address})"
