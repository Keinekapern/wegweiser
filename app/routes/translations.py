from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import categories
from app.category_names import KEYS as CATEGORY_KEYS, category_name
from app.deps import templates
from app.i18n import (TRANSIT_KINDS, DIRECTIONS_LANGUAGES, DirectionsText, DOC_KEYS, DOC_STRINGS, MANEUVER_KEYS, MANEUVERS,
                      directions_language_options, get_ui_lang, normalize_directions_lang)

router = APIRouter()

# English explanation per key, so reviewers know the context
_CONTEXT_EN = {
    "car": "mode: by car", "foot": "mode: on foot", "summary": "distance + duration",
    "minutes": "duration in minutes", "hours": "duration in hours and minutes",
    "steps": "heading of turn-by-turn list", "created": "creation date on the printout",
    "osm": "map data credit", "date": "date format (strftime)",
    "qr_hint": "text under the QR codes", "transit": "mode: public transport",
    "connection": "heading of the connection", "walk_to_stop": "walking leg to a stop",
    "walk_to_dest": "last walking leg", "direction": "direction of a bus/train",
    "every_min": "frequency (minutes)", "every_hours": "frequency (hours)",
    "timetable_note": "timetable disclaimer", "platform": "platform/track",
    "alternatives": "other connections", "roundabout": "enter roundabout, take exit {n}",
}


class _Ride:
    """Minimal ride leg for the examples of transit_modes()."""
    kind = "transit"

    def __init__(self, mode: str):
        self.mode = mode


@router.get("/translations", response_class=HTMLResponse)
def translations_page(request: Request, lang: str | None = None):
    lang = normalize_directions_lang(lang or "ar")
    rows = [(key, _CONTEXT_EN.get(key, ""), DOC_STRINGS["de"][key], DOC_STRINGS["en"][key],
             DOC_STRINGS[lang][key]) for key in DOC_KEYS]
    maneuvers = []
    if lang in MANEUVERS:
        maneuvers = [(key, _CONTEXT_EN.get(key, key.replace("_", " ")), MANEUVERS[lang][key])
                     for key in MANEUVER_KEYS]
    category_rows = [(key, categories.BY_KEY[key].label, category_name(key, "en"),
                      category_name(key, lang)) for key in CATEGORY_KEYS]
    # Means of transport: each kind alone plus typical combinations
    kind_modes = {"bus": "BUS", "tram": "TRAM", "metro": "SUBWAY", "train": "REGIONAL_RAIL",
                  "ferry": "FERRY", "cable": "AERIAL_LIFT"}
    combos = [(k,) for k in TRANSIT_KINDS] + [("bus", "train"), ("bus", "ferry"),
                                              ("bus", "tram", "train")]
    mode_rows = []
    for combo in combos:
        legs = [_Ride(kind_modes[k]) for k in combo]
        mode_rows.append((" + ".join(combo), DirectionsText("de").transit_modes(legs),
                          DirectionsText("en").transit_modes(legs),
                          DirectionsText(lang).transit_modes(legs)))
    return templates.TemplateResponse(request, "translations.html", {
        "lang": lang, "languages": directions_language_options(get_ui_lang(request)),
        "html_lang": DIRECTIONS_LANGUAGES[lang][1], "rtl": DIRECTIONS_LANGUAGES[lang][2],
        "rows": rows, "maneuvers": maneuvers, "category_rows": category_rows,
        "mode_rows": mode_rows,
    })
