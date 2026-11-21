"""Settings pages (admins; everyone with AUTH_MODE=off)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app import config, languages
from app.services import backup
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
