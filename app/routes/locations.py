from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import categories, db
from app.deps import DB, templates
from app.i18n import get_ui_lang, translate
from app.validation import coordinates_from_form, required_text

router = APIRouter(prefix="/locations")


def _join(lat, lon) -> str:
    return f"{lat}, {lon}" if lat not in (None, "") and lon not in (None, "") else ""


def validate_location_form(name: str, address: str, coords: str, lat: str = "", lon: str = ""):
    errors: list = []
    name = required_text(name, "Name", errors)
    address = required_text(address, "Adresse", errors)
    lat_v, lon_v = coordinates_from_form({"coords": coords, "lat": lat, "lon": lon}, errors)
    return errors, (name, address, lat_v, lon_v)


def render_locations(request: Request, conn, *, form=None, errors=None,
                     edit_id: int | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "locations.html",
        {
            "locations": db.list_locations(conn),
            "form": form or {},
            "errors": errors or [],
            "edit_id": edit_id,
            "location_icon": categories.LOCATION_ICON,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def locations_page(request: Request, conn: DB):
    return render_locations(request, conn)


@router.post("", response_class=HTMLResponse)
def locations_create(
    request: Request,
    conn: DB,
    name: Annotated[str, Form()] = "",
    address: Annotated[str, Form()] = "",
    coords: Annotated[str, Form()] = "",
    lat: Annotated[str, Form()] = "",
    lon: Annotated[str, Form()] = "",
):
    errors, values = validate_location_form(name, address, coords, lat, lon)
    if errors:
        form = {"name": name, "address": address, "coords": coords or _join(lat, lon)}
        return render_locations(request, conn, form=form, errors=errors, status_code=422)
    db.create_location(conn, *values)
    return RedirectResponse("/locations", status_code=303)


@router.get("/{location_id}/edit", response_class=HTMLResponse)
def locations_edit(request: Request, conn: DB, location_id: int):
    loc = db.get_location(conn, location_id)
    if loc is None:
        raise HTTPException(404, translate(get_ui_lang(request), "Standort nicht gefunden"))
    form = {"name": loc.name, "address": loc.address, "coords": _join(loc.lat, loc.lon)}
    return render_locations(request, conn, form=form, edit_id=location_id)


@router.post("/{location_id}", response_class=HTMLResponse)
def locations_update(
    request: Request,
    conn: DB,
    location_id: int,
    name: Annotated[str, Form()] = "",
    address: Annotated[str, Form()] = "",
    coords: Annotated[str, Form()] = "",
    lat: Annotated[str, Form()] = "",
    lon: Annotated[str, Form()] = "",
):
    if db.get_location(conn, location_id) is None:
        raise HTTPException(404, translate(get_ui_lang(request), "Standort nicht gefunden"))
    errors, values = validate_location_form(name, address, coords, lat, lon)
    if errors:
        form = {"name": name, "address": address, "coords": coords or _join(lat, lon)}
        return render_locations(request, conn, form=form, errors=errors,
                                edit_id=location_id, status_code=422)
    db.update_location(conn, location_id, *values)
    return RedirectResponse("/locations", status_code=303)


@router.post("/{location_id}/delete")
def locations_delete(request: Request, conn: DB, location_id: int):
    if not db.delete_location(conn, location_id):
        raise HTTPException(404, translate(get_ui_lang(request), "Standort nicht gefunden"))
    return RedirectResponse("/locations", status_code=303)
