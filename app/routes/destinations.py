from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
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
                edit_id: int | None = None, status_code: int = 200, search_query: str = ""):
    return templates.TemplateResponse(
        request, "destination_form.html",
        {"form": form, "errors": errors or [], "edit_id": edit_id, "search_query": search_query,
         "can_assign": auth.can(request, "destination.assign_locations"),
         "creates_pending": auth.creates_pending(request),
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
def destinations_new(request: Request, conn: DB, location_id: str | None = None,
                     name: str | None = None):
    # Preselect the location from the list filter / directions page; with a single
    # location, that one. "name" comes from "create new destination" in the picker:
    # it prefills the name and starts the OSM search with it.
    locations = db.list_locations(conn)
    preselect = _int_or_none(location_id)
    if preselect is None and len(locations) == 1:
        preselect = locations[0].id
    name = (name or "").strip()[:200]
    form = {"location_ids": [preselect] if preselect else [], "name": name}
    return render_form(request, conn, form=form, search_query=name)


def _creator_locations(conn, location_ids: list[int]) -> list[int]:
    """Without login, assigning destinations to locations is not allowed; only the location
    the form was opened from is kept, so the new destination shows up there."""
    known = {loc.id for loc in db.list_locations(conn)}
    return [i for i in location_ids if i in known][:1]


@router.post("", response_class=HTMLResponse)
async def destinations_create(request: Request, conn: DB):
    form = await read_form(request, conn)
    errors, dest = validate_destination_form(form)
    if errors:
        return render_form(request, conn, form=form, errors=errors, status_code=422)
    if not auth.creates_pending(request):
        dest_id = db.create_destination(conn, dest)
        db.set_destination_locations(conn, dest_id, form["location_ids"])
        db.set_destination_names(conn, dest_id, form["names"])
        return RedirectResponse("/destinations", status_code=303)
    creator, new_cookie = auth.ensure_creator_token(request)
    dest_id = db.create_destination(conn, dest, pending=True, creator_token=creator)
    db.set_destination_locations(conn, dest_id, _creator_locations(conn, form["location_ids"]))
    db.set_destination_names(conn, dest_id, form["names"])
    response = RedirectResponse("/destinations?created=pending", status_code=303)
    if new_cookie:
        auth.set_cookie(response, request, auth.CREATOR_COOKIE, new_cookie,
                        auth.CREATOR_COOKIE_DAYS * 86400)
    return response


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
        db.set_destination_locations(conn, destination_id, form["location_ids"])
    db.set_destination_names(conn, destination_id, form["names"])
    return RedirectResponse("/destinations", status_code=303)


@router.post("/{destination_id}/delete")
def destinations_delete(request: Request, conn: DB, destination_id: int):
    _editable_destination(request, conn, destination_id, "destination.delete")
    db.delete_destination(conn, destination_id)
    back = "/admin" if "/admin" in request.headers.get("referer", "") else "/destinations"
    return RedirectResponse(back, status_code=303)
