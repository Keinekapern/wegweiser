"""Folder and file names in the PDF export (ZIP).

    Wegweiser_2026-11-21_EA-Tübingen.zip          one location: destinations at the top
    Wegweiser_2026-11-21_3-Standorte.zip          several: one folder per location first
      Übersicht.pdf
      EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Arabisch.pdf

File name = "<destination> – <language>[ – <mode>].pdf": the destination is in the file
name too, so a single file sent or printed on its own is still clear. Languages, modes
and fixed names are in the UI language of the person exporting (staff need not know
language codes); the mode is only added when the export contains more than one. Names
are safe on Windows and kept short.
"""

import re
from datetime import date

from app import db
from app.i18n import LANGUAGE_NAMES, translate

MAX_PART = 80                       # per folder/file name, keeps paths below 260 chars
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Export modes (directions profiles) and how they appear in file names (msgids)
MODE_LABELS = {"auto": "automatisch", "transit": "ÖPNV", "foot-walking": "zu Fuß"}


def overview_name(ui: str = "de") -> str:
    return translate(ui, "Übersicht") + ".pdf"


def mode_label(mode: str, ui: str = "de") -> str:
    """German as written ("ÖPNV", "zu Fuß"); other languages lower case like "on foot"
    ("ÖPNV" shares its translation "Public transport" with the UI label)."""
    label = translate(ui, MODE_LABELS.get(mode, mode))
    return label if ui == "de" else label[:1].lower() + label[1:]


def safe(name: str, limit: int = MAX_PART, ui: str = "de") -> str:
    """A folder/file name that works on Windows, macOS and Linux."""
    name = _FORBIDDEN.sub("-", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > limit:
        cut = name[:limit]
        name = cut.rsplit(" ", 1)[0] if " " in cut[limit // 2:] else cut
    name = name.rstrip(" .")
    return name or translate(ui, "Ohne Namen")


def language_name(code: str, ui: str = "de") -> str:
    """Name in the UI language, e.g. "Arabisch"; "Persisch / Farsi" -> "Persisch (Farsi)"."""
    name = translate(ui, LANGUAGE_NAMES.get(code, code))
    first, sep, rest = name.partition(" / ")
    return f"{first} ({rest})" if sep else name


def _street(address: str) -> str:
    return address.split(",")[0].strip()


def destination_folders(destinations: list[db.Destination]) -> dict[int, str]:
    """destination id -> folder name; equal names get the street, then the id."""
    base = {d.id: safe(d.name) for d in destinations}
    counts: dict[str, int] = {}
    for name in base.values():
        counts[name.lower()] = counts.get(name.lower(), 0) + 1
    names = {}
    for d in destinations:
        name = base[d.id]
        if counts[name.lower()] > 1:
            name = safe(f"{d.name} ({_street(d.address)})")
        names[d.id] = name
    # still equal (same name and street): make them unique with the id
    seen: dict[str, int] = {}
    for d in destinations:
        seen[names[d.id].lower()] = seen.get(names[d.id].lower(), 0) + 1
    for d in destinations:
        if seen[names[d.id].lower()] > 1:
            names[d.id] = safe(f"{names[d.id]} {d.id}")
    return names


def pdf_name(folder: str, lang: str, mode: str | None = None, ui: str = "de") -> str:
    parts = [folder, language_name(lang, ui)]
    if mode:
        parts.append(mode_label(mode, ui))
    return safe(" – ".join(parts), MAX_PART + 30) + ".pdf"


def location_folders(locations: list[db.Location]) -> dict[int, str]:
    names = {loc.id: safe(loc.name) for loc in locations}
    seen: dict[str, int] = {}
    for n in names.values():
        seen[n.lower()] = seen.get(n.lower(), 0) + 1
    return {i: (safe(f"{n} {i}") if seen[n.lower()] > 1 else n) for i, n in names.items()}


def zip_name(locations: list[db.Location], day: date, ui: str = "de") -> str:
    if len(locations) == 1:
        label = safe(locations[0].name, 40).replace(" ", "-")
    else:
        label = translate(ui, "{n} Standorte", n=len(locations)).replace(" ", "-")
    return f"Wegweiser_{day.isoformat()}_{label}.zip"
