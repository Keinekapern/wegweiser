"""Settings pages (admins; everyone with AUTH_MODE=off)."""

import json

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from app import categories, config, db, languages, print_options
from app.services import backup, data_transfer
from app.deps import DB, Allowed, templates
from app.i18n import DEFAULT_DIRECTIONS_LANG, Msg, directions_language_options, get_ui_lang

router = APIRouter(prefix="/settings")


def _render(request: Request, conn, notice=None):
    return templates.TemplateResponse(request, "settings_languages.html", {
        "all_languages": directions_language_options(get_ui_lang(request)),
        "enabled": set(languages.enabled(conn)),
        "default_lang": DEFAULT_DIRECTIONS_LANG,
        "notice": notice,
    })


@router.get("/languages", response_class=HTMLResponse)
def languages_page(request: Request, conn: DB, _: Allowed("settings.languages")):
    return _render(request, conn)


@router.post("/languages", response_class=HTMLResponse)
async def languages_save(request: Request, conn: DB, _: Allowed("settings.languages")):
    form = await request.form()
    chosen = languages.set_enabled(conn, form.getlist("langs"))
    return _render(request, conn, notice=Msg("Gespeichert: {n} Sprachen stehen zur Auswahl.",
                                             n=len(chosen)))


# --- printout ---

def _render_print(request: Request, conn, notice=None):
    return templates.TemplateResponse(request, "settings_print.html", {
        "credit": print_options.credit_enabled(conn),
        "credit_text": print_options.credit_text(),
        "notice": notice,
    })


@router.get("/print", response_class=HTMLResponse)
def print_page(request: Request, conn: DB, _: Allowed("settings.print")):
    return _render_print(request, conn)


@router.post("/print", response_class=HTMLResponse)
async def print_save(request: Request, conn: DB, _: Allowed("settings.print")):
    form = await request.form()
    print_options.set_credit(conn, form.get("credit") == "1")
    return _render_print(request, conn, notice=Msg("Gespeichert."))


# --- database backups ---

def _render_backups(request: Request, notice=None, error=None, status_code=200):
    last_error, last_error_at = backup.last_error()
    return templates.TemplateResponse(request, "settings_backup.html", {
        "backups": backup.list_backups(),
        "directory": config.backup_dir(),
        "enabled": config.backup_enabled(),
        "keep": config.backup_keep(),
        "time": "%02d:%02d" % config.backup_time(),
        "last_error": error or last_error,
        "last_error_at": last_error_at,
        "notice": notice,
    }, status_code=status_code)


@router.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request, _: Allowed("settings.backup")):
    return _render_backups(request)


@router.post("/backup", response_class=HTMLResponse)
def backup_now(request: Request, _: Allowed("settings.backup")):
    try:
        made = backup.create_backup()
    except Exception as exc:
        return _render_backups(request, error=str(exc), status_code=500)
    return _render_backups(request, notice=Msg("Sicherung erstellt: {name}", name=made.name))


@router.get("/backup/{name}")
def backup_download(name: str, _: Allowed("settings.backup")):
    found = next((b for b in backup.list_backups() if b.name == name), None)  # no paths
    if found is None:
        raise HTTPException(404)
    return FileResponse(found.path, media_type="application/vnd.sqlite3", filename=found.name)


# --- export and import of destinations and locations ---


def _download(content: str | bytes, filename: str, media_type: str) -> Response:
    from app.routes.export import _content_disposition
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": _content_disposition(filename)})


def _render_data(request: Request, conn, *, errors=None, status_code=200):
    return templates.TemplateResponse(request, "settings_data.html", {
        "errors": errors or [],
        "counts": {"destinations": len(db.list_destinations(conn)),
                   "locations": len(db.list_locations(conn))},
        "max_mb": data_transfer.MAX_BYTES // (1024 * 1024),
    }, status_code=status_code)


@router.get("/data", response_class=HTMLResponse)
def data_page(request: Request, conn: DB, _: Allowed("data.transfer")):
    return _render_data(request, conn)


@router.get("/data/export")
def data_export(request: Request, conn: DB, _: Allowed("data.transfer"),
                format: str = "json", locations: str = "0", pending: str = "0"):
    from datetime import date
    from app.i18n import translate
    ui = get_ui_lang(request)
    day = date.today().isoformat()
    with_locations, with_pending = locations == "1", pending == "1"
    if format == "csv-locations":
        return _download(data_transfer.export_locations_csv(conn),
                         f"Wegweiser_{translate(ui, 'Standorte')}_{day}.csv", "text/csv; charset=utf-8")
    if format == "csv":
        return _download(data_transfer.export_destinations_csv(conn, with_locations, with_pending),
                         f"Wegweiser_{translate(ui, 'Ziele')}_{day}.csv", "text/csv; charset=utf-8")
    data = data_transfer.export_json(conn, with_locations, with_pending)
    return _download(json.dumps(data, ensure_ascii=False, indent=2),
                     f"Wegweiser_{translate(ui, 'Daten')}_{day}.json", "application/json")


@router.post("/data/import", response_class=HTMLResponse)
async def data_import_read(request: Request, conn: DB, file: UploadFile,
                           _: Allowed("data.transfer")):
    content = await file.read(data_transfer.MAX_BYTES + 1)
    try:
        plan = data_transfer.read(conn, file.filename or "", content)
    except data_transfer.ImportError_ as exc:
        return _render_data(request, conn, errors=[exc.msg], status_code=422)
    return templates.TemplateResponse(request, "settings_import.html", {
        "plan": plan, "field_label": data_transfer.field_label,
        "category_label": lambda key: (categories.get(key).label if categories.get(key) else ""),
    })


@router.post("/data/import/{token}", response_class=HTMLResponse)
async def data_import_apply(request: Request, conn: DB, token: str, _: Allowed("data.transfer")):
    plan = data_transfer.get_plan(token)
    if plan is None:
        return _render_data(request, conn, status_code=410, errors=[
            Msg("Die Vorschau ist abgelaufen. Bitte die Datei noch einmal hochladen.")])
    form = await request.form()
    chosen = set()
    for key in form.getlist("update"):
        kind, _sep, line = key.partition(":")
        if kind in ("location", "destination") and line.isdigit():
            chosen.add((kind, int(line)))
    result = data_transfer.apply(conn, plan, chosen)
    return templates.TemplateResponse(request, "settings_data.html", {
        "errors": [], "result": result,
        "counts": {"destinations": len(db.list_destinations(conn)),
                   "locations": len(db.list_locations(conn))},
        "max_mb": data_transfer.MAX_BYTES // (1024 * 1024),
    })
