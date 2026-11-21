"""Automatic database backups."""

import sqlite3
from datetime import datetime

import pytest

from app import db
from app.services import backup


@pytest.fixture
def backups(client, tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_KEEP", "3")
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    with db.get_conn() as conn:
        db.cache_put(conn, "ors|x", "{}")
    return tmp_path / "backups"


def test_backup_keeps_data_without_cache(backups):
    made = backup.create_backup(datetime(2026, 11, 21, 2, 30))
    assert made.name == "wegweiser-2026-11-21_0230.sqlite"
    copy = sqlite3.connect(made.path)
    assert copy.execute("SELECT name FROM locations").fetchall() == [("EA",)]
    assert copy.execute("SELECT COUNT(*) FROM api_cache").fetchone() == (0,)
    assert copy.execute("SELECT COUNT(*) FROM admins").fetchone() == (1,)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert not list(backups.glob("*.part"))


def test_rotation_keeps_the_newest(backups):
    for day in range(1, 6):
        backup.create_backup(datetime(2026, 11, day, 2, 30))
    assert [b.name for b in backup.list_backups()] == [
        "wegweiser-2026-11-05_0230.sqlite", "wegweiser-2026-11-04_0230.sqlite",
        "wegweiser-2026-11-03_0230.sqlite"]
    (backups / "notes.txt").write_text("not a backup")     # other files stay untouched
    backup.rotate()
    assert (backups / "notes.txt").exists()


def test_schedule(backups, monkeypatch):
    monkeypatch.setenv("BACKUP_TIME", "02:30")
    assert backup.next_run(datetime(2026, 11, 21, 1, 0)) == datetime(2026, 11, 21, 2, 30)
    assert backup.next_run(datetime(2026, 11, 21, 3, 0)) == datetime(2026, 11, 22, 2, 30)
    assert not backup.backed_up_today(datetime(2026, 11, 21, 3, 0))
    backup.create_backup(datetime(2026, 11, 21, 3, 0))
    assert backup.backed_up_today(datetime(2026, 11, 21, 23, 0))
    monkeypatch.setenv("BACKUP_TIME", "25:00")
    with pytest.raises(ValueError):
        backup.next_run(datetime(2026, 11, 21))


def test_failed_backup_is_reported(backups, client, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("BACKUP_DIR", str(blocker / "sub"))     # cannot create a folder there
    r = client.post("/settings/backup")
    assert r.status_code == 500 and "Die letzte Sicherung ist fehlgeschlagen" in r.text
    monkeypatch.setenv("BACKUP_DIR", str(backups))
    client.post("/settings/backup")
    assert "Die letzte Sicherung ist fehlgeschlagen" not in client.get("/settings/backup").text


def test_backup_page_and_download(backups, client, anon_client):
    page = client.get("/settings/backup").text
    assert "Noch keine Sicherung" in page and "behält die letzten 3" in page
    r = client.post("/settings/backup")
    assert "Sicherung erstellt: wegweiser-" in r.text
    name = backup.list_backups()[0].name
    dl = client.get(f"/settings/backup/{name}")
    assert dl.status_code == 200 and dl.content[:15] == b"SQLite format 3"
    assert client.get("/settings/backup/..%2Ftest.sqlite").status_code == 404
    assert client.get("/settings/backup/other.sqlite").status_code == 404
    assert anon_client.get(f"/settings/backup/{name}", follow_redirects=False).status_code == 303
    assert "/settings/backup" in client.get("/admin").text
