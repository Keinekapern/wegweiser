import json
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth, categories, db, languages
from app.deps import DB, templates
from app.i18n import (DIRECTIONS_LANGUAGES, directions_language_options, get_ui_lang,
                      translate)
from app.validation import (coordinates_from_form, optional_google_maps_url, optional_osm_ref,
                            optional_phone, optional_url, required_text)

router = APIRouter(prefix="/destinations")

FORM_FIELDS = ("name", "address", "coords", "lat", "lon", "phone", "website", "opening_hours",
               "google_maps_url", "note", "osm_type", "osm_id", "category")
# Translated names: one optional field per directions language except German (the original)
NAME_LANGS = tuple(code for code in DIRECTIONS_LANGUAGES if code != "de")
# Bulk entry: lines searched one by one in Nominatim (1 request/s), so keep it small
MAX_BULK = 30


def validate_destination_form(form: dict[str, str]) -> tuple[list[str], db.Destination | None]:
    errors: list[str] = []
    name = required_text(form["name"], "Name", errors)
    address = required_text(form["address"], "Adresse", errors)
    lat, lon = coordinates_from_form(form, errors)
    phone = optional_phone(form["phone"], errors)
    website = optional_url(form["website"], "Website", errors)
    google = optional_google_maps_url(form["google_maps_url"], errors)
    osm_type, osm_id = optional_osm_ref(form["osm_type"], form["osm_id"])
    if errors:
        return errors, None
    return [], db.Destination(
        id=None, name=name, address=address, lat=lat, lon=lon,
        phone=phone, website=website,
        opening_hours=form["opening_hours"].strip(), google_maps_url=google,
        note=form["note"].strip(), osm_type=osm_type, osm_id=osm_id,
        category=form["category"] if categories.get(form["category"]) else "",
    )


def _int_list(values) -> list[int]:
    result = []
    for v in values:
        try:
            result.append(int(v))
        except (TypeError, ValueError):
            pass
    return result


def _int_or_none(raw: str | None) -> int | None:
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


async def read_form(request: Request, conn) -> dict:
    data = await request.form()
    form: dict = {f: str(data.get(f, "")) for f in FORM_FIELDS}
    form["location_ids"] = _int_list(data.getlist("location_ids"))
    # only the languages shown in the form (names in switched-off languages are kept)
    shown = set(languages.enabled(conn))
    form["names"] = {lang: str(data.get(f"name_{lang}", "")).strip()[:200]
                     for lang in NAME_LANGS if lang in shown}
    return form


def _name_languages(request: Request, conn) -> list[dict]:
    """Enabled directions languages for the translated-name fields, sorted like the menu."""
    options = languages.options(conn, get_ui_lang(request))
    return [{"code": code, "native": native, "label": ui_name,
             "html_lang": DIRECTIONS_LANGUAGES[code][1], "rtl": DIRECTIONS_LANGUAGES[code][2]}
            for code, (native, ui_name) in options.items() if code in NAME_LANGS]


def render_form(request: Request, conn, *, form: dict, errors=None,
                edit_id: int | None = None, status_code: int = 200, search_query: str = "",
                saved: db.Destination | None = None):
    return templates.TemplateResponse(
        request, "destination_form.html",
        {"form": form, "errors": errors or [], "edit_id": edit_id, "search_query": search_query,
         "saved": saved,
         **_location_context(request, conn),
         "locations": db.list_locations(conn), "categories": categories.CATEGORIES,
         "category_groups": categories.GROUPS, "name_languages": _name_languages(request, conn)},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def destinations_page(request: Request, conn: DB, location_id: str | None = None):
    locations = db.list_locations(conn)
    filter_id = _int_or_none(location_id)
    if filter_id is not None and not any(loc.id == filter_id for loc in locations):
        filter_id = None
    dests = db.list_destinations(conn, filter_id)
    return templates.TemplateResponse(request, "destinations.html", {
        "destinations": dests,
        "editable": {d.id for d in dests if auth.can(request, "destination.edit", d, conn)},
        "created_pending": request.query_params.get("created") == "pending",
        "locations": locations,
        "location_names": {loc.id: loc.name for loc in locations},
        "assignments": db.destination_location_ids(conn),
        "filter_id": filter_id,
        "categories": categories.BY_KEY,
    })


@router.get("/new", response_class=HTMLResponse)
def destinations_new(request: Request, conn: DB,
                     location_id: Annotated[list[str] | None, Query()] = None,
                     name: str | None = None, saved: str | None = None):
    # Preselect the location(s) from the list filter / directions page / the destination
    # saved before ("Anlegen und nächstes Ziel"); with a single location, that one.
    # "name" comes from "create new destination" in the picker: it prefills the name
    # and starts the OSM search with it.
    form = {"location_ids": _preselected(request, conn, location_id), "name": (name or "").strip()[:200]}
    saved_dest = db.get_destination(conn, _int_or_none(saved) or 0) if saved else None
    return render_form(request, conn, form=form, search_query=form["name"], saved=saved_dest)


def _preselected(request: Request, conn, raw_ids: list[str] | None) -> list[int]:
    known = {loc.id for loc in db.list_locations(conn)}
    ids = [i for i in _int_list(raw_ids or []) if i in known]
    if not ids and len(known) == 1:
        ids = list(known)
    if not ids and auth.home_locations(request):
        ids = [auth.home_locations(request)[0]]
    return ids


def _assignable(request: Request, conn) -> list[db.Location]:
    """Locations offered as checkboxes in the form (managers: only their own)."""
    allowed = auth.assignable_locations(request)
    return [loc for loc in db.list_locations(conn) if allowed is None or loc.id in allowed]


def _assigned(request: Request, conn, location_ids: list[int]) -> list[int]:
    """Locations to store for a destination created or changed with assignment rights.
    Managers may only use their own; none ticked = all of their own (a destination for
    all locations is up to the admins)."""
    allowed = auth.assignable_locations(request)
    if allowed is None:
        return location_ids
    return [i for i in location_ids if i in allowed] or sorted(allowed)


def _creator_locations(request: Request, conn, location_ids: list[int]) -> list[int]:
    """Proposals cannot choose locations: staff proposals go to their own locations (to
    the one the form was opened from, if it is theirs), so their managers can approve
    them; without login only the location the form was opened from is kept."""
    home = auth.home_locations(request)
    if home:
        return [i for i in location_ids if i in home][:1] or list(home)
    known = {loc.id for loc in db.list_locations(conn)}
    return [i for i in location_ids if i in known][:1]


def _save_new(request: Request, conn, dest: db.Destination, location_ids: list[int],
              names: dict[str, str], creator: str | None) -> int:
    """Store a new destination; creator = hash of the browser's creator cookie if it
    becomes a proposal (auth.creates_pending), else None."""
    if creator is None:
        dest_id = db.create_destination(conn, dest)
        db.set_destination_locations(conn, dest_id, _assigned(request, conn, location_ids))
    else:
        dest_id = db.create_destination(conn, dest, pending=True, creator_token=creator)
        db.set_destination_locations(conn, dest_id, _creator_locations(request, conn, location_ids))
    db.set_destination_names(conn, dest_id, names)
    return dest_id


def _creator(request: Request) -> tuple[str | None, str | None]:
    """(creator hash or None for approved destinations, new cookie value or None)"""
    if not auth.creates_pending(request):
        return None, None
    return auth.ensure_creator_token(request)


def _with_creator_cookie(response, request: Request, new_cookie: str | None):
    if new_cookie:
        auth.set_cookie(response, request, auth.CREATOR_COOKIE, new_cookie,
                        auth.CREATOR_COOKIE_DAYS * 86400)
    return response


@router.post("", response_class=HTMLResponse)
async def destinations_create(request: Request, conn: DB):
    form = await read_form(request, conn)
    errors, dest = validate_destination_form(form)
    if errors:
        return render_form(request, conn, form=form, errors=errors, status_code=422)
    creator, new_cookie = _creator(request)
    dest_id = _save_new(request, conn, dest, form["location_ids"], form["names"], creator)
    if (await request.form()).get("next"):
        # "Anlegen und nächstes Ziel": empty form, same locations ticked
        stored = db.locations_of_destination(conn, dest_id) if form["location_ids"] else []
        query = "".join(f"&location_id={i}" for i in stored)
        target = f"/destinations/new?saved={dest_id}{query}"
    else:
        target = "/destinations?created=pending" if creator else "/destinations"
    return _with_creator_cookie(RedirectResponse(target, status_code=303), request, new_cookie)


def _location_context(request: Request, conn) -> dict:
    return {"can_assign": auth.can(request, "destination.assign_locations"),
            "assign_locations": _assignable(request, conn),
            "assign_all": auth.assignable_locations(request) is None,
            "creates_pending": auth.creates_pending(request)}


def render_bulk(request: Request, conn, *, location_ids: list[int], created=(), skipped=()):
    existing = {f"{t}/{i}": name for t, i, name in conn.execute(
        "SELECT osm_type, osm_id, name FROM destinations WHERE COALESCE(osm_type, '') <> '' AND osm_id IS NOT NULL")}
    return templates.TemplateResponse(request, "destination_bulk.html", {
        **_location_context(request, conn),
        "form": {"location_ids": location_ids}, "max_lines": MAX_BULK, "existing": existing,
        "categories": categories.CATEGORIES, "category_groups": categories.GROUPS,
        "created": list(created), "skipped": list(skipped)})


@router.get("/bulk", response_class=HTMLResponse)
def destinations_bulk(request: Request, conn: DB,
                      location_id: Annotated[list[str] | None, Query()] = None):
    return render_bulk(request, conn, location_ids=_preselected(request, conn, location_id))


def _bulk_item(raw: str, shown: set[str]) -> tuple[dict, dict[str, str]] | None:
    """One chosen OSM hit from the bulk page: (form fields, translated names)."""
    try:
        item = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(item, dict):
        return None
    form = {f: "" if item.get(f) is None else str(item[f]) for f in FORM_FIELDS}
    names = item.get("names") if isinstance(item.get("names"), dict) else {}
    names = {lang: str(v).strip()[:200] for lang, v in names.items()
             if lang in NAME_LANGS and lang in shown and str(v).strip()}
    return form, names


@router.post("/bulk", response_class=HTMLResponse)
async def destinations_bulk_create(request: Request, conn: DB):
    data = await request.form()
    location_ids = _int_list(data.getlist("location_ids"))
    shown = set(languages.enabled(conn))
    creator, new_cookie = _creator(request)
    created, skipped = [], []
    for raw in data.getlist("item")[:MAX_BULK]:
        parsed = _bulk_item(str(raw), shown)
        if parsed is None:
            continue
        form, names = parsed
        errors, dest = validate_destination_form(form)
        if errors:
            skipped.append((form["name"].strip() or "?", errors))
            continue
        dest_id = _save_new(request, conn, dest, location_ids, names, creator)
        created.append((dest_id, dest.name))
    response = render_bulk(request, conn, location_ids=location_ids, created=created,
                           skipped=skipped)
    return _with_creator_cookie(response, request, new_cookie)


def _editable_destination(request: Request, conn, destination_id: int,
                          action: str = "destination.edit") -> db.Destination:
    """The destination if this browser may change it; 404 if missing, login otherwise."""
    dest = db.get_destination(conn, destination_id)
    if dest is None:
        raise HTTPException(404, translate(get_ui_lang(request), "Ziel nicht gefunden"))
    auth.require(request, action, dest, conn)
    return dest


@router.get("/{destination_id}/edit", response_class=HTMLResponse)
def destinations_edit(request: Request, conn: DB, destination_id: int):
    dest = _editable_destination(request, conn, destination_id)
    form = {f: getattr(dest, f) for f in FORM_FIELDS if hasattr(dest, f)}
    form["coords"] = f"{dest.lat}, {dest.lon}"
    form["location_ids"] = db.destination_location_ids(conn).get(destination_id, [])
    form["names"] = db.get_destination_names(conn, destination_id)
    return render_form(request, conn, form=form, edit_id=destination_id)


@router.post("/{destination_id}", response_class=HTMLResponse)
async def destinations_update(request: Request, conn: DB, destination_id: int):
    _editable_destination(request, conn, destination_id)
    form = await read_form(request, conn)
    errors, dest = validate_destination_form(form)
    if errors:
        return render_form(request, conn, form=form, errors=errors, edit_id=destination_id,
                           status_code=422)
    db.update_destination(conn, destination_id, dest)
    if auth.can(request, "destination.assign_locations"):   # creators cannot change it
        db.set_destination_locations(conn, destination_id,
                                     _assigned(request, conn, form["location_ids"]))
    db.set_destination_names(conn, destination_id, form["names"])
    return RedirectResponse("/destinations", status_code=303)


@router.post("/{destination_id}/delete")
def destinations_delete(request: Request, conn: DB, destination_id: int):
    _editable_destination(request, conn, destination_id, "destination.delete")
    db.delete_destination(conn, destination_id)
    back = "/admin" if "/admin" in request.headers.get("referer", "") else "/destinations"
    return RedirectResponse(back, status_code=303)
