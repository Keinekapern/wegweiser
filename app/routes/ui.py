from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.i18n import UI_LANG_COOKIE, UI_LANGUAGES

router = APIRouter()


def _safe_next(next_url: str) -> str:
    # Only local paths, no open redirect ("//host" or "/\\host")
    if not next_url.startswith("/") or next_url.startswith(("//", "/\\")):
        return "/"
    return next_url


@router.get("/ui-language/{lang}", include_in_schema=False)
def set_ui_language(lang: str, next: str = "/"):
    resp = RedirectResponse(_safe_next(next), status_code=303)
    if lang in UI_LANGUAGES:
        resp.set_cookie(UI_LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp
