from dataclasses import dataclass, field
from datetime import date
from sqlite3 import Connection
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import categories, db
from app.category_names import category_name
from app.deps import DB, templates
from app.i18n import (DirectionsText, Msg, directions_language_options, get_ui_lang,
                      normalize_directions_lang)
from app.services import line_symbols
from app.services.qr import map_links
from app.services.routing import ATTRIBUTION, PROFILES, OrsClient, RoutingError, get_router
from app.services.transit import (MODE_GROUP_LABELS, SOURCES_URL, WEEKDAYS, TransitError,
                                  TransitousClient, TransitSettings, common_place, get_transit,
                                  stop_icon, without_place,
                                  load_defaults, save_defaults)

router = APIRouter(prefix="/directions")

Router = Annotated[OrsClient, Depends(get_router)]
Transit = Annotated[TransitousClient, Depends(get_transit)]

# Modes offered in the UI (German msgids). "auto" picks walking or public transport;
# the bicycle is never chosen automatically.
UI_PROFILES = {"auto": "Automatisch", "foot-walking": "Zu Fuß", "transit": "ÖPNV",
               "cycling-regular": PROFILES["cycling-regular"]}


SETTING_FIELDS = ("max_transfers", "walk_start_min", "walk_end_min", "weekday", "time",
                  "auto_walk_max_min")


def _int_or_none(raw: str | None) -> int | None:
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def transit_settings_from_request(request: Request, conn: Connection,
                                  errors: list[Msg]) -> TransitSettings:
    """Explicit options from the form/URL (transit_opts=1), otherwise stored defaults."""
    params = request.query_params
    if params.get("transit_opts") != "1":
        return load_defaults(conn)
    raw = {k: params.get(k) for k in SETTING_FIELDS}
    raw["modes"] = params.getlist("modes")
    raw["wheelchair"] = params.get("wheelchair", "0")
    return TransitSettings.parse(raw, errors)


def build_context(conn: Connection, router_: OrsClient, transit: TransitousClient,
                  transit_settings: TransitSettings, location_id: str | None,
                  destination_id: str | None, profile: str, lang: str | None) -> dict:
    """Selection, route and map data shared by the directions page and the print view."""
    locations = db.list_locations(conn)
    loc_id, dest_id = _int_or_none(location_id), _int_or_none(destination_id)
    assignments = db.destination_location_ids(conn)
    if loc_id is None and len(locations) == 1:
        loc_id = locations[0].id
    elif loc_id is None and dest_id is not None and len(assignments.get(dest_id, [])) == 1:
        # e.g. "Route" button in the destination list: start at the destination's location
        loc_id = assignments[dest_id][0]
    if profile not in UI_PROFILES:
        profile = "auto"
    doc_lang = normalize_directions_lang(lang)
    dt = DirectionsText(doc_lang)

    location = db.get_location(conn, loc_id) if loc_id else None
    destination = db.get_destination(conn, dest_id) if dest_id else None
    route, error, symbol_credits, auto_reason, details = None, None, [], None, []
    if location and destination:
        start, end = (location.lat, location.lon), (destination.lat, destination.lon)
        try:
            if profile == "auto":
                route, auto_reason = choose_automatically(
                    conn, router_, transit, transit_settings, start, end, doc_lang)
            elif profile == "transit":
                route, _cached = transit.plan(conn, start, end, transit_settings,
                                              language=doc_lang)
            else:
                route, _cached = router_.route(conn, profile, start, end, language=doc_lang)
            if route is not None and route.profile == "transit":
                symbol_credits = line_symbols.attach(conn, route)
                # Start and destination in one place: drop it from stop names everywhere
                route = without_place(route, common_place(location.address, destination.address))
                details = walk_details(conn, router_, route, location, destination, doc_lang)
        except (RoutingError, TransitError) as exc:
            error = exc.msg
    elif (loc_id and not location) or (dest_id and not destination):
        error = Msg("Standort oder Ziel wurde nicht gefunden.")

    map_data = None
    if location and destination:
        map_data = {
            "start": {"name": location.name, "lat": location.lat, "lon": location.lon,
                      "icon": f"/static/{categories.LOCATION_ICON}"},
            "end": {"name": destination.name, "lat": destination.lat, "lon": destination.lon,
                    "icon": (f"/static/{categories.get(destination.category).image}"
                             if categories.get(destination.category) else None)},
            "route": route.to_dict() if route else None,
            "walk_details": [d.to_dict() for d in details],
            "attribution": dt("osm"),
        }

    selected = {"location_id": loc_id, "destination_id": dest_id, "profile": profile,
                "lang": doc_lang}
    # Links (print view) use the effective mode, so the printout shows exactly this route
    effective = route.profile if (profile == "auto" and route is not None) else profile
    items = [(k, v) for k, v in (selected | {"profile": effective}).items() if v is not None]
    if effective in ("transit", "auto"):
        items += transit_settings.query_items()
    query = urlencode(items)
    return {
        "locations": locations,
        "selected": selected,
        "query": query,
        "location": location,
        "destination": destination,
        "route": route,
        "error": error,
        "map_data": map_data,
        "dt": dt,
        "today": date.today(),
        "route_attribution": ATTRIBUTION,
        "transit_settings": transit_settings,
        "transit_sources_url": SOURCES_URL,
        "symbol_credits": symbol_credits,
        "dest_category": categories.get(destination.category) if destination else None,
        "dest_subtitle": destination_subtitle(conn, destination, doc_lang) if destination else "",
        "location_icon": categories.LOCATION_ICON,
        "auto_reason": auto_reason,
        "walk_details": details,
    }


MIN_DETAIL_WALK_S = 60   # shorter walks get no detail map


@dataclass
class WalkDetail:
    """Detail view of the walk start -> first stop or last stop -> destination."""
    kind: str                    # "to_stop" | "to_dest"
    stop: str                    # stop name
    duration_s: float
    distance_m: float | None
    start: dict                  # {"lat", "lon", "name"}
    end: dict
    geometry: list[list[float]]
    steps: list = field(default_factory=list)   # routing.Step (from ORS, if available)
    stop_mode: str = ""          # MOTIS mode of the ride at this stop (picks the stop sign)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "start": self.start, "end": self.end,
                "geometry": self.geometry, "stop_icon": f"/static/{stop_icon(self.stop_mode)}"}


def destination_subtitle(conn: Connection, destination, lang: str) -> str:
    """Line under the destination name in the directions language: the translated name
    if one is stored ("Kinderklinik" -> "Children's hospital"), otherwise the kind of
    place ("Fielmann" -> "Optician")."""
    text = (db.get_destination_names(conn, destination.id).get(lang)
            or category_name(destination.category, lang))
    return "" if text == destination.name else text


def walk_details(conn: Connection, router_: OrsClient, plan, location, destination,
                 lang: str) -> list[WalkDetail]:
    """Walking legs to the first and from the last stop, re-routed with openrouteservice
    for exact paths and turn-by-turn texts in the directions language (cached). Falls
    back to the Transitous geometry without texts."""
    legs = plan.legs
    candidates = []
    if legs and legs[0].kind == "walk":
        leg = legs[0]
        candidates.append(("to_stop", leg, leg.to_name, legs[1].mode if len(legs) > 1 else "",
                           {"lat": location.lat, "lon": location.lon, "name": location.name},
                           {"lat": leg.to_lat, "lon": leg.to_lon, "name": leg.to_name}))
    if len(legs) > 1 and legs[-1].kind == "walk":
        leg = legs[-1]
        candidates.append(("to_dest", leg, leg.from_name, legs[-2].mode,
                           {"lat": leg.from_lat, "lon": leg.from_lon, "name": leg.from_name},
                           {"lat": destination.lat, "lon": destination.lon,
                            "name": destination.name}))
    details = []
    for kind, leg, stop, stop_mode, start, end in candidates:
        if leg.duration_s < MIN_DETAIL_WALK_S or None in (start["lat"], end["lat"]):
            continue
        detail = WalkDetail(kind, stop, leg.duration_s, leg.distance_m, start, end, leg.geometry,
                            stop_mode=stop_mode)
        try:
            walk, _ = router_.route(conn, "foot-walking", (start["lat"], start["lon"]),
                                    (end["lat"], end["lon"]), language=lang)
            # Path, distance and texts from ORS; the duration stays the timetable's, so
            # the detail map and the connection list on the same sheet agree
            detail.geometry, detail.steps = walk.geometry, walk.steps
            detail.distance_m = walk.distance_m
        except RoutingError:
            pass   # keep the Transitous geometry
        details.append(detail)
    return details


def choose_automatically(conn: Connection, router_: OrsClient, transit: TransitousClient,
                         settings: TransitSettings, start: tuple[float, float],
                         end: tuple[float, float], lang: str):
    """Walk for short distances, otherwise public transport if it is faster.

    Returns (route, reason as Msg). Raises if not even a walking route is available.
    """
    try:
        walk, _ = router_.route(conn, "foot-walking", start, end, language=lang)
    except RoutingError:
        # No walking route (e.g. ORS unavailable): public transport is the only option
        plan, _ = transit.plan(conn, start, end, settings, language=lang)
        return plan, None
    walk_min = max(1, round(walk.duration_s / 60))
    if walk_min <= settings.auto_walk_max_min:
        return walk, Msg("Automatisch gewählt: zu Fuß – der Fußweg dauert nur {walk} Min. "
                         "(Grenze: {limit} Min.).", walk=walk_min, limit=settings.auto_walk_max_min)
    try:
        plan, _ = transit.plan(conn, start, end, settings, language=lang)
    except TransitError as exc:
        return walk, Msg("Automatisch gewählt: zu Fuß – keine ÖPNV-Verbindung verfügbar "
                         "({error})", error=exc.msg)
    transit_min = max(1, round(plan.duration_s / 60))
    if transit_min < walk_min:
        return plan, Msg("Automatisch gewählt: ÖPNV – {transit} Min. statt {walk} Min. zu Fuß.",
                         transit=transit_min, walk=walk_min)
    return walk, Msg("Automatisch gewählt: zu Fuß – mit Bus und Bahn nicht schneller "
                     "({transit} statt {walk} Min.).", transit=transit_min, walk=walk_min)


def group_by_category(destinations: list) -> list[tuple[str, object, list]]:
    """[(group label msgid, category or None, destinations)] in category order,
    destinations without category last; names sorted within each group."""
    groups = []
    for cat in categories.CATEGORIES:
        items = [d for d in destinations if d.category == cat.key]
        if items:
            groups.append((cat.label, cat, items))
    rest = [d for d in destinations if not categories.get(d.category)]
    if rest:
        groups.append(("Ohne Kategorie", None, rest))
    return groups


def selection_options(conn: Connection, request: Request) -> dict:
    destinations = db.list_destinations(conn)
    return {
        "destinations": destinations,
        "dest_groups": group_by_category(destinations),
        # destination id -> assigned location ids (empty = offered for all locations)
        "assignments": db.destination_location_ids(conn),
        "profiles": UI_PROFILES,
        "mode_groups": MODE_GROUP_LABELS,
        "weekdays": WEEKDAYS,
        # code -> (native name, name as UI msgid)
        "directions_languages": directions_language_options(get_ui_lang(request)),
    }


@router.get("", response_class=HTMLResponse)
def directions_page(
    request: Request,
    conn: DB,
    router_: Router,
    transit: Transit,
    location_id: str | None = None,
    destination_id: str | None = None,
    profile: str = "auto",
    lang: str | None = None,
):
    errors: list[Msg] = []
    settings = transit_settings_from_request(request, conn, errors)
    ctx = build_context(conn, router_, transit, settings, location_id, destination_id,
                        profile, lang)
    ctx["option_errors"] = errors
    ctx["saved"] = request.query_params.get("saved") == "1"
    return templates.TemplateResponse(request, "directions.html", ctx | selection_options(conn, request))


@router.get("/print", response_class=HTMLResponse)
def directions_print(
    request: Request,
    conn: DB,
    router_: Router,
    transit: Transit,
    location_id: str | None = None,
    destination_id: str | None = None,
    profile: str = "auto",
    lang: str | None = None,
):
    settings = transit_settings_from_request(request, conn, [])
    ctx = build_context(conn, router_, transit, settings, location_id, destination_id,
                        profile, lang)
    if not (ctx["location"] and ctx["destination"]):
        ctx["error"] = ctx["error"] or Msg("Standort oder Ziel wurde nicht gefunden.")
        return templates.TemplateResponse(request, "directions.html",
                                          ctx | selection_options(conn, request), status_code=404)
    ctx["map_links"] = map_links(ctx["destination"], ctx["dt"]("apple_maps"))
    return templates.TemplateResponse(request, "print.html", ctx)


@router.post("/transit-defaults")
async def save_transit_defaults(request: Request, conn: DB):
    """Save the public transport options of the form as defaults, then show the route."""
    form = await request.form()
    errors: list[Msg] = []
    raw = {k: form.get(k) for k in SETTING_FIELDS}
    raw["modes"] = form.getlist("modes")
    raw["wheelchair"] = form.get("wheelchair", "0")
    settings = TransitSettings.parse(raw, errors)
    items = [(k, str(form.get(k))) for k in ("location_id", "destination_id", "profile", "lang")
             if form.get(k)]
    if errors:
        # Show the form again with the errors (options are kept in the URL)
        return RedirectResponse("/directions?" + urlencode(items + [("transit_opts", "1")] + [
            (k, str(v)) for k, v in form.multi_items() if k in raw]), status_code=303)
    save_defaults(conn, settings)
    return RedirectResponse("/directions?" + urlencode(items + [("saved", "1")]), status_code=303)
