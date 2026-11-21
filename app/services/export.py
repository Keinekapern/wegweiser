"""Bulk export: PDFs for selected locations x destinations x languages x modes as one ZIP.

Jobs run one at a time in a background thread (one Chromium, see pdf.py); progress is
kept in memory, the ZIP in data/exports/ for an hour. Structure and names: export_names.
"""

import logging
import secrets
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from app import config, db, export_names
from app.services import pdf

log = logging.getLogger(__name__)

KEEP_SECONDS = 3600
MAX_FILES = 600            # PDFs per export (about half an hour of rendering)
MODES = tuple(export_names.MODE_LABELS)
# Reasons listed in Übersicht.pdf (German msgids, translated there)
INCOMPLETE_MAP = "Karte unvollständig (Kacheln fehlen)"
FAILED_PAGE = "Seite konnte nicht erstellt werden"
FAILED_RENDER = "Fehler beim Erstellen"


@dataclass
class ExportRequest:
    location_ids: list[int]
    destination_ids: list[int]
    langs: list[str]
    modes: list[str]
    orientation: str = "portrait"
    bw: bool = False
    ui_lang: str = "de"            # language of folder and file names


@dataclass
class Item:
    location: db.Location
    destination: db.Destination
    lang: str
    mode: str
    path: str                      # inside the ZIP

    def print_url(self, req: ExportRequest) -> str:
        return "/directions/print?" + urlencode({
            "location_id": self.location.id, "destination_id": self.destination.id,
            "profile": self.mode, "lang": self.lang, "orientation": req.orientation,
            "bw": "1" if req.bw else "0"})


@dataclass
class Job:
    id: str
    request: ExportRequest
    items: list[Item]
    zip_name: str
    status: str = "queued"         # queued | running | done | failed
    done: int = 0
    current: str = ""
    problems: list[tuple[str, str]] = field(default_factory=list)   # (path, reason)
    error: str = ""
    created: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def zip_path(self) -> Path:
        return export_dir() / f"{self.id}.zip"

    def as_dict(self) -> dict:
        size = self.zip_path.stat().st_size if self.status == "done" and self.zip_path.exists() else 0
        return {"status": self.status, "done": self.done, "total": self.total,
                "current": self.current, "problems": len(self.problems), "error": self.error,
                "size": size}


def export_dir() -> Path:
    return config.database_path().parent / "exports"


def offered(conn, location_id: int, destination_ids: list[int]) -> list[db.Destination]:
    """Selected destinations that are offered for this location (assigned or unassigned)."""
    wanted = set(destination_ids)
    return [d for d in db.list_destinations(conn, location_id) if d.id in wanted]


def plan(conn, req: ExportRequest) -> tuple[list[Item], str]:
    """All PDFs of the export with their path in the ZIP, and the ZIP's name."""
    from app.i18n import DIRECTIONS_LANGUAGES
    req.langs = [l for l in req.langs if l in DIRECTIONS_LANGUAGES]
    locations = [loc for loc in db.list_locations(conn) if loc.id in set(req.location_ids)]
    loc_folders = export_names.location_folders(locations)
    with_mode = len(req.modes) > 1
    items = []
    for loc in locations:
        dests = offered(conn, loc.id, req.destination_ids)
        folders = export_names.destination_folders(dests)
        for dest in dests:
            base = f"{loc_folders[loc.id]}/" if len(locations) > 1 else ""
            for lang in sorted(req.langs, key=lambda c: export_names.language_name(c, req.ui_lang)):
                for mode in req.modes:
                    name = export_names.pdf_name(folders[dest.id], lang,
                                                 mode if with_mode else None, req.ui_lang)
                    items.append(Item(loc, dest, lang, mode, f"{base}{folders[dest.id]}/{name}"))
    return items, export_names.zip_name(locations, date.today(), req.ui_lang)


# --- jobs ---

_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")


def cleanup() -> None:
    """Forget jobs and delete ZIPs older than an hour."""
    limit = time.time() - KEEP_SECONDS
    with _jobs_lock:
        for job_id in [j.id for j in _jobs.values() if j.created < limit and j.status != "running"]:
            _jobs.pop(job_id).zip_path.unlink(missing_ok=True)
    if export_dir().exists():
        for f in export_dir().glob("*.zip"):
            if f.stat().st_mtime < limit:
                f.unlink(missing_ok=True)


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def busy() -> bool:
    return any(j.status in ("queued", "running") for j in _jobs.values())


def start(conn, req: ExportRequest, overview_html) -> Job:
    """overview_html(job) -> HTML of Übersicht.pdf (rendered after all PDFs)."""
    cleanup()
    items, name = plan(conn, req)
    job = Job(id=secrets.token_urlsafe(12), request=req, items=items, zip_name=name)
    with _jobs_lock:
        _jobs[job.id] = job
    _executor.submit(run, job, overview_html)
    return job


def run(job: Job, overview_html) -> None:
    job.status = "running"
    export_dir().mkdir(parents=True, exist_ok=True)
    tmp = job.zip_path.with_suffix(".part")
    try:
        with pdf.open_renderer() as renderer, \
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in job.items:
                job.current = item.path
                try:
                    data, state, error = renderer.render(item.print_url(job.request))
                except Exception as exc:          # one bad page must not end the export
                    log.warning("Export %s: %s", item.path, exc)
                    data, state, error = b"", "errors", FAILED_RENDER
                if error or not data:
                    job.problems.append((item.path, error or FAILED_PAGE))
                else:
                    zf.writestr(item.path, data)
                    if state != "ok":
                        job.problems.append((item.path, INCOMPLETE_MAP))
                job.done += 1
            job.current = export_names.overview_name(job.request.ui_lang)
            zf.writestr(job.current, renderer.render_html(overview_html(job)))
        tmp.replace(job.zip_path)
        job.status = "done"
        job.current = ""
    except Exception as exc:
        log.exception("Export failed")
        tmp.unlink(missing_ok=True)
        job.status = "failed"
        job.error = str(exc)
