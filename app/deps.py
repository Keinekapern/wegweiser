from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection
from typing import Annotated

from fastapi import Depends
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import db
from app.i18n import i18n_context
from app.services.transit import same_place_names, stop_icon

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates", context_processors=[i18n_context])


def isolate(text: str) -> Markup:
    """Inserted name (e.g. a German line destination) as its own bidi run, so in
    right-to-left directions it keeps its place instead of merging with its neighbours."""
    return Markup('<span class="bidi-isolate">{}</span>').format(text)


def stop_name(name: str, mode: str | None = None) -> Markup:
    """Stop name with the stop sign for the mode in front ("H" for bus/tram, train,
    U-Bahn, ferry, cable car); not used for line destinations/headsigns."""
    return Markup('<span class="stop-name"><img class="stop-symbol" src="/static/{}" alt="" '
                  'aria-hidden="true">{}</span>').format(stop_icon(mode), escape(name))


templates.env.globals["stop_name"] = stop_name
templates.env.globals["isolate"] = isolate
templates.env.globals["same_place_names"] = same_place_names


def get_db() -> Iterator[Connection]:
    with db.get_conn() as conn:
        yield conn


DB = Annotated[Connection, Depends(get_db)]
