from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import db
from app.i18n import i18n_context
from app.services.transit import same_place_names, stop_icon

BASE_DIR = Path(__file__).parent
def auth_context(request: Request) -> dict:
    """Jinja2 context processor: logged-in admin and the number of destinations awaiting
    approval (shown in the navigation)."""
    from app.auth import current_admin
    admin = current_admin(request)
    pending = 0
    if admin is not None:
        with db.get_conn() as conn:
            pending = db.count_pending_destinations(conn)
    return {"admin": admin, "pending_count": pending}


templates = Jinja2Templates(directory=BASE_DIR / "templates",
                            context_processors=[i18n_context, auth_context])


def isolate(text: str) -> Markup:
    """Inserted name (e.g. a German line destination) as its own bidi run, so in
    right-to-left directions it keeps its place instead of merging with its neighbours."""
    return Markup('<span class="bidi-isolate">{}</span>').format(text)


def stop_name(name: str, mode: str | None = None) -> Markup:
    """Stop name with the stop sign for the mode in front ("H" for bus/tram, train,
    U-Bahn, ferry, cable car); not used for line destinations/headsigns."""
    return Markup('<span class="stop-name"><img class="stop-symbol" src="/static/{}" alt="" '
                  'aria-hidden="true">{}</span>').format(stop_icon(mode), escape(name))


def dt_local(utc: str) -> str:
    """SQLite datetime('now') (UTC) as local date and time, e.g. "17.11.2026, 14:05"."""
    try:
        moment = datetime.strptime(utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return utc or ""
    return moment.astimezone().strftime("%d.%m.%Y, %H:%M")


templates.env.globals["dt_local"] = dt_local
templates.env.globals["stop_name"] = stop_name
templates.env.globals["isolate"] = isolate
templates.env.globals["same_place_names"] = same_place_names


def get_db() -> Iterator[Connection]:
    with db.get_conn() as conn:
        yield conn


DB = Annotated[Connection, Depends(get_db)]


def _require_admin(request: Request):
    from app.auth import require_admin
    return require_admin(request)


AdminUser = Annotated[db.Admin, Depends(_require_admin)]
