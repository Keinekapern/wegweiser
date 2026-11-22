"""Export and import of destinations and locations (JSON and CSV).

JSON ("wegweiser-data", version 1) keeps everything: translated names, categories and,
if chosen, the locations and which destinations are offered where (by location name,
ids differ between instances). CSV is for spreadsheets: one row per destination or
location, separator ";", UTF-8 with BOM (Excel), coordinates as "lat, lon" in one
column so Excel does not turn them into numbers.

Import is two steps: read() parses and checks every row and compares it with what is
there (same OSM object, otherwise same name and address) -> new / same / changed /
invalid; apply() then adds the new rows and updates the changed ones the user chose.
Locations are never part of an export unless chosen (accommodation addresses).
"""

import csv
import io
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date

from app import categories, db
from app.i18n import DIRECTIONS_LANGUAGES, LANGUAGE_NAMES, Msg

FORMAT = "wegweiser-data"
VERSION = 1
MAX_BYTES = 5 * 1024 * 1024
KEEP_SECONDS = 1800          # how long a read file waits for its confirmation

NAME_LANGS = [c for c in DIRECTIONS_LANGUAGES if c != "de"]
DEST_FIELDS = ("name", "address", "lat", "lon", "phone", "website", "opening_hours",
               "google_maps_url", "note", "osm_type", "osm_id", "category")
# CSV columns (German headers; English ones are accepted on import)
DEST_COLUMNS = [("name", "Name"), ("address", "Adresse"), ("coords", "Koordinaten"),
                ("phone", "Telefon"), ("website", "Website"), ("opening_hours", "Öffnungszeiten"),
                ("google_maps_url", "Google-Maps-Link"), ("note", "Notiz"),
                ("osm_type", "OSM-Typ"), ("osm_id", "OSM-ID"), ("category", "Kategorie")]
LOC_COLUMNS = [("name", "Name"), ("address", "Adresse"), ("coords", "Koordinaten")]
LOCATIONS_COLUMN = "Standorte"           # names separated by " | "
ENGLISH_HEADERS = {"address": "Address", "coords": "Coordinates", "phone": "Phone",
                   "opening_hours": "Opening hours", "google_maps_url": "Google Maps link",
                   "note": "Note", "osm_type": "OSM type", "osm_id": "OSM ID",
                   "category": "Category", "locations": "Locations"}
SEP = " | "


def _coords(lat, lon) -> str:
    return f"{lat}, {lon}"


def _category_label(key: str) -> str:
    cat = categories.get(key)
    return cat.label if cat else ""


def _category_key(value: str) -> str:
    value = (value or "").strip()
    if categories.get(value):
        return value
    for c in categories.CATEGORIES:
        if value.casefold() in (c.label.casefold(), c.key):
            return c.key
    return ""


def _destinations(conn, with_pending: bool) -> list[db.Destination]:
    return [d for d in db.list_destinations(conn) if with_pending or not d.pending]


# --- export ---

def export_json(conn, with_locations: bool, with_pending: bool = False) -> dict:
    locations = db.list_locations(conn)
    names = {loc.id: loc.name for loc in locations}
    assignments = db.destination_location_ids(conn)
    dests = []
    for d in _destinations(conn, with_pending):
        entry = {f: getattr(d, f) for f in DEST_FIELDS}
        entry["names"] = db.get_destination_names(conn, d.id)
        if with_locations:
            entry["locations"] = [names[i] for i in assignments.get(d.id, []) if i in names]
        dests.append(entry)
    data = {"format": FORMAT, "version": VERSION, "exported": date.today().isoformat(),
            "destinations": dests}
    if with_locations:
        data["locations"] = [{"name": l.name, "address": l.address, "lat": l.lat, "lon": l.lon}
                             for l in locations]
    return data


def _csv_text(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return "﻿" + buf.getvalue()


def export_destinations_csv(conn, with_locations: bool, with_pending: bool = False) -> str:
    locations = {loc.id: loc.name for loc in db.list_locations(conn)}
    assignments = db.destination_location_ids(conn)
    header = [h for _, h in DEST_COLUMNS]
    if with_locations:
        header.append(LOCATIONS_COLUMN)
    header += [f"Name ({c})" for c in NAME_LANGS]
    rows = []
    for d in _destinations(conn, with_pending):
        row = [d.name, d.address, _coords(d.lat, d.lon), d.phone, d.website, d.opening_hours,
               d.google_maps_url, d.note, d.osm_type or "", d.osm_id or "",
               _category_label(d.category)]
        if with_locations:
            row.append(SEP.join(locations[i] for i in assignments.get(d.id, []) if i in locations))
        names = db.get_destination_names(conn, d.id)
        row += [names.get(c, "") for c in NAME_LANGS]
        rows.append(row)
    return _csv_text(header, rows)


def export_locations_csv(conn) -> str:
    return _csv_text([h for _, h in LOC_COLUMNS],
                     [[l.name, l.address, _coords(l.lat, l.lon)] for l in db.list_locations(conn)])


# --- import: read and compare ---

@dataclass
class Row:
    kind: str                       # "location" | "destination"
    line: int                       # row in the file (1 = first data row)
    values: dict                    # validated fields
    names: dict = field(default_factory=dict)        # translated names (destinations)
    locations: list[str] | None = None               # None = file says nothing about it
    errors: list = field(default_factory=list)
    status: str = "new"             # new | same | changed | invalid
    existing_id: int | None = None
    changes: list[tuple[str, str, str]] = field(default_factory=list)  # (field, old, new)

    @property
    def label(self) -> str:
        return self.values.get("name") or f"#{self.line}"


@dataclass
class ImportPlan:
    token: str
    filename: str
    rows: list[Row]
    created: float = field(default_factory=time.time)
    unknown_locations: set[str] = field(default_factory=set)

    def of(self, kind: str, status: str) -> list[Row]:
        return [r for r in self.rows if r.kind == kind and r.status == status]


class ImportError_(ValueError):
    """The file as a whole cannot be read (message is a Msg)."""

    def __init__(self, msg: Msg):
        super().__init__(msg.msgid)
        self.msg = msg


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def _validate_location(raw: dict, line: int) -> Row:
    from app.routes.locations import validate_location_form
    errors, (name, address, lat, lon) = validate_location_form(
        str(raw.get("name", "")), str(raw.get("address", "")), str(raw.get("coords", "")),
        str(raw.get("lat", "")), str(raw.get("lon", "")))
    return Row("location", line, {"name": name, "address": address, "lat": lat, "lon": lon},
               errors=errors, status="invalid" if errors else "new")


def _validate_destination(raw: dict, line: int, names: dict, locations) -> Row:
    from app.routes.destinations import validate_destination_form
    form = {f: str(raw.get(f, "") if raw.get(f) is not None else "")
            for f in ("name", "address", "coords", "lat", "lon", "phone", "website",
                      "opening_hours", "google_maps_url", "note", "osm_type", "osm_id")}
    form["category"] = _category_key(str(raw.get("category", "")))
    errors, dest = validate_destination_form(form)
    values = {f: getattr(dest, f) for f in DEST_FIELDS} if dest else {"name": form["name"]}
    names = {c: str(n).strip()[:200] for c, n in (names or {}).items()
             if c in NAME_LANGS and str(n).strip()}
    return Row("destination", line, values, names=names, locations=locations,
               errors=errors, status="invalid" if errors else "new")


def _headers(header: list[str], columns: list[tuple[str, str]]) -> dict[int, str]:
    """column index -> field (German or English header)."""
    lookup = {}
    for key, german in columns + [("locations", LOCATIONS_COLUMN)]:
        lookup[german.casefold()] = key
        lookup[ENGLISH_HEADERS.get(key, german).casefold()] = key
    out = {}
    for i, h in enumerate(header):
        h = h.strip().lstrip("﻿")
        m = re.fullmatch(r"name \(([a-z]{2,3})\)", h.casefold())
        if m:
            out[i] = "name_" + m.group(1)
        elif h.casefold() in lookup:
            out[i] = lookup[h.casefold()]
    return out


def _read_csv(text: str) -> list[Row]:
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise ImportError_(Msg("Die Datei ist leer."))
    cols = _headers(header, DEST_COLUMNS)
    fields = set(cols.values())
    if not {"name", "address"} <= fields or not ({"coords"} <= fields or {"lat", "lon"} <= fields):
        raise ImportError_(Msg("Die CSV-Datei braucht mindestens die Spalten Name, Adresse und Koordinaten."))
    is_destinations = bool(fields & {"phone", "website", "opening_hours", "category", "osm_id",
                                     "google_maps_url", "note", "locations"}
                           or any(f.startswith("name_") for f in fields))
    rows = []
    for n, record in enumerate(reader, start=1):
        if not any(cell.strip() for cell in record):
            continue
        raw = {cols[i]: cell.strip() for i, cell in enumerate(record) if i in cols}
        if is_destinations:
            names = {k[5:]: v for k, v in raw.items() if k.startswith("name_")}
            locs = ([s.strip() for s in raw.get("locations", "").split("|") if s.strip()]
                    if "locations" in fields else None)
            rows.append(_validate_destination(raw, n, names, locs))
        else:
            rows.append(_validate_location(raw, n))
    return rows


def _read_json(text: str) -> list[Row]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ImportError_(Msg("Die Datei ist kein gültiges JSON."))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ImportError_(Msg("Das ist keine Export-Datei von Wegweiser."))
    if int(data.get("version", 0)) > VERSION:
        raise ImportError_(Msg("Die Datei stammt aus einer neueren Wegweiser-Version."))
    rows = [_validate_location(l, n) for n, l in enumerate(data.get("locations") or [], 1)
            if isinstance(l, dict)]
    for n, d in enumerate(data.get("destinations") or [], 1):
        if isinstance(d, dict):
            locs = d.get("locations")
            rows.append(_validate_destination(d, n, d.get("names") or {},
                                              [str(x) for x in locs] if isinstance(locs, list) else None))
    return rows


def _compare(conn, rows: list[Row]) -> set[str]:
    locations = db.list_locations(conn)
    by_key = {(_norm(l.name), _norm(l.address)): l for l in locations}
    known_names = {_norm(l.name) for l in locations} | {_norm(r.values["name"]) for r in rows
                                                        if r.kind == "location" and r.status != "invalid"}
    dests = db.list_destinations(conn)
    by_osm = {(d.osm_type, d.osm_id): d for d in dests if d.osm_type and d.osm_id}
    by_name = {(_norm(d.name), _norm(d.address)): d for d in dests}
    names_of = {loc.id: loc.name for loc in locations}
    assignments = db.destination_location_ids(conn)
    unknown = set()
    for r in rows:
        if r.status == "invalid":
            continue
        v = r.values
        if r.kind == "location":
            old = by_key.get((_norm(v["name"]), _norm(v["address"])))
            if old:
                r.existing_id = old.id
                r.changes = [(f, str(getattr(old, f)), str(v[f])) for f in ("lat", "lon")
                             if abs(float(getattr(old, f)) - float(v[f])) > 1e-6]
                r.status = "changed" if r.changes else "same"
            continue
        old = by_osm.get((v.get("osm_type"), v.get("osm_id"))) if v.get("osm_id") else None
        old = old or by_name.get((_norm(v["name"]), _norm(v["address"])))
        for name in r.locations or []:
            if _norm(name) not in known_names:
                unknown.add(name)
        if old is None:
            continue
        r.existing_id = old.id
        changes = []
        for f in DEST_FIELDS:
            a, b = getattr(old, f), v.get(f)
            if f in ("lat", "lon"):
                if abs(float(a) - float(b)) > 1e-6:
                    changes.append((f, str(a), str(b)))
            elif (a or "") != (b or ""):
                changes.append((f, str(a or ""), str(b or "")))
        old_names = db.get_destination_names(conn, old.id)
        for c, n in r.names.items():
            if old_names.get(c, "") != n:
                changes.append((f"name_{c}", old_names.get(c, ""), n))
        if r.locations is not None:
            have = sorted(names_of[i] for i in assignments.get(old.id, []) if i in names_of)
            want = sorted(n for n in r.locations if _norm(n) in known_names)
            if [_norm(x) for x in have] != [_norm(x) for x in want]:
                changes.append(("locations", SEP.join(have), SEP.join(want)))
        r.changes = changes
        r.status = "changed" if changes else "same"
    return unknown


_plans: dict[str, ImportPlan] = {}


def read(conn, filename: str, content: bytes) -> ImportPlan:
    """Parse and compare an uploaded file; the plan waits for apply() (30 minutes)."""
    limit = time.time() - KEEP_SECONDS
    for t in [t for t, p in _plans.items() if p.created < limit]:
        _plans.pop(t, None)
    if len(content) > MAX_BYTES:
        raise ImportError_(Msg("Die Datei ist zu groß (höchstens 5 MB)."))
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")   # Excel's "CSV" on Windows
    stripped = text.lstrip()
    rows = _read_json(text) if stripped.startswith("{") else _read_csv(text)
    if not rows:
        raise ImportError_(Msg("Die Datei enthält keine Ziele oder Standorte."))
    unknown = _compare(conn, rows)
    plan = ImportPlan(secrets.token_urlsafe(12), filename, rows, unknown_locations=unknown)
    _plans[plan.token] = plan
    return plan


def get_plan(token: str) -> ImportPlan | None:
    return _plans.get(token)


# --- import: apply ---

@dataclass
class Result:
    added: int = 0
    updated: int = 0
    skipped: int = 0


def apply(conn, plan: ImportPlan, update_lines: set[tuple[str, int]]) -> Result:
    """Add new rows, update the changed rows listed in update_lines ((kind, line))."""
    res = Result()
    # locations first, destinations refer to them by name
    for r in plan.rows:
        if r.kind != "location":
            continue
        v = r.values
        if r.status == "new":
            db.create_location(conn, v["name"], v["address"], v["lat"], v["lon"])
            res.added += 1
        elif r.status == "changed" and ("location", r.line) in update_lines:
            db.update_location(conn, r.existing_id, v["name"], v["address"], v["lat"], v["lon"])
            res.updated += 1
        else:
            res.skipped += 1
    loc_ids = {_norm(l.name): l.id for l in db.list_locations(conn)}
    for r in plan.rows:
        if r.kind != "destination":
            continue
        if r.status == "new":
            dest_id = db.create_destination(conn, db.Destination(id=None, **r.values))
            res.added += 1
        elif r.status == "changed" and ("destination", r.line) in update_lines:
            dest_id = r.existing_id
            db.update_destination(conn, dest_id, db.Destination(id=dest_id, **r.values))
            res.updated += 1
        else:
            res.skipped += 1
            continue
        if r.names:
            db.set_destination_names(conn, dest_id, r.names)
        if r.locations is not None:
            db.set_destination_locations(conn, dest_id,
                                         [loc_ids[_norm(n)] for n in r.locations if _norm(n) in loc_ids])
    _plans.pop(plan.token, None)
    return res


def field_label(name: str) -> str:
    """German msgid for a field in the import preview."""
    labels = {"name": "Name", "address": "Adresse", "lat": "Breitengrad", "lon": "Längengrad",
              "phone": "Telefon", "website": "Website", "opening_hours": "Öffnungszeiten",
              "google_maps_url": "Google-Maps-Link", "note": "Notiz", "osm_type": "OSM-Typ",
              "osm_id": "OSM-ID", "category": "Kategorie", "locations": "Standorte"}
    if name.startswith("name_"):
        return LANGUAGE_NAMES.get(name[5:], name[5:])
    return labels.get(name, name)
