"""Automatic database backups.

Once a day (BACKUP_TIME, local time, default 02:30) the app writes a consistent copy of
the SQLite database with VACUUM INTO, checks it (PRAGMA integrity_check) and keeps the
newest BACKUP_KEEP copies (default 14). The copy leaves out what can be rebuilt any
time (API cache, admin sessions), so it holds locations, destinations, names, settings
and admin accounts.

BACKUP_DIR should be on a second medium (external disk, a folder synced to a cloud
drive): in Docker it is the volume ./backups, see BACKUP_PATH in docker-compose.yml.
Restore: stop the app, copy a backup over data/wegweiser.sqlite, start it again.
"""

import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app import config

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^wegweiser-(\d{4}-\d{2}-\d{2})_(\d{4})\.sqlite$")
# Rebuilt automatically, not worth keeping in a backup
DROPPED_TABLES = ("api_cache", "admin_sessions", "api_usage")

_lock = threading.Lock()
_state = {"last_error": "", "last_error_at": None}


@dataclass
class Backup:
    path: Path
    created: datetime
    size: int

    @property
    def name(self) -> str:
        return self.path.name


def backup_dir() -> Path:
    return config.backup_dir()


def list_backups() -> list[Backup]:
    """Newest first."""
    d = backup_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        m = NAME_RE.match(p.name)
        if m and p.is_file():
            created = datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M")
            out.append(Backup(p, created, p.stat().st_size))
    return sorted(out, key=lambda b: b.created, reverse=True)


def last_error() -> tuple[str, datetime | None]:
    return _state["last_error"], _state["last_error_at"]


def create_backup(now: datetime | None = None) -> Backup:
    """Write, check and rotate one backup; raises on failure (and remembers the error)."""
    now = now or datetime.now()
    with _lock:
        try:
            d = backup_dir()
            d.mkdir(parents=True, exist_ok=True)
            target = d / f"wegweiser-{now:%Y-%m-%d_%H%M}.sqlite"
            tmp = target.with_suffix(".part")
            tmp.unlink(missing_ok=True)
            src = sqlite3.connect(config.database_path())
            try:
                src.execute("VACUUM INTO ?", (str(tmp),))
            finally:
                src.close()
            copy = sqlite3.connect(tmp)
            try:
                for table in DROPPED_TABLES:
                    copy.execute(f"DELETE FROM {table}")   # names from the constant above
                copy.commit()
                copy.execute("VACUUM")
                result = copy.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                copy.close()
            if result != "ok":
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"integrity check of the copy failed: {result}")
            tmp.replace(target)
            rotate()
            _state.update(last_error="", last_error_at=None)
            log.info("Backup written: %s", target)
            return Backup(target, now.replace(second=0, microsecond=0), target.stat().st_size)
        except Exception as exc:
            _state.update(last_error=str(exc), last_error_at=now)
            log.error("Backup failed: %s", exc)
            raise


def rotate() -> None:
    keep = config.backup_keep()
    if keep <= 0:                  # automatic backups off: keep manual ones
        return
    for old in list_backups()[keep:]:
        old.path.unlink(missing_ok=True)


def backed_up_today(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return any(b.created.date() == now.date() for b in list_backups())


def next_run(now: datetime) -> datetime:
    hour, minute = config.backup_time()
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


def _loop(stop: threading.Event) -> None:
    # After a start (e.g. the server was off at night): catch up on a missed backup
    now = datetime.now()
    hour, minute = config.backup_time()
    if not backed_up_today(now) and (now.hour, now.minute) >= (hour, minute):
        _safe_backup()
    while not stop.is_set():
        now = datetime.now()
        if stop.wait(max(1.0, (next_run(now) - now).total_seconds())):
            break
        _safe_backup()


def _safe_backup() -> None:
    try:
        create_backup()
    except Exception:        # already logged and shown on the admin page
        pass


def start_scheduler() -> threading.Event | None:
    """Daily backups in a background thread; returns the event that stops it."""
    if not config.backup_enabled():
        log.info("Automatic backups switched off (BACKUP_KEEP=0)")
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="backup", daemon=True).start()
    return stop
