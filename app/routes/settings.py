"""Settings pages (admins; everyone with AUTH_MODE=off)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import languages
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
