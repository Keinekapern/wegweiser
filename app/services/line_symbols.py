"""Pictograms next to line numbers and line colours from regional add-ons (app/regions.py,
e.g. TüBus Tübingen: line 1 = cat, official network-map colours).

A region covers an area (bounding box) and some modes; a transit leg gets the symbol and
the line colour if its boarding stop lies inside the area and the region lists its line.
Regional colours override the timetable's (also for lines run by subcontractors); lines
without any colour get one by mode (transit.fallback_color, after the DB signage colours).
"""

import sqlite3

from app import regions
from app.regions import Region
from app.services.transit import TransitPlan, fallback_color


def _lookup(sets: tuple[Region, ...], mode: str, line: str,
            lat: float | None, lon: float | None) -> tuple[dict | None, str | None]:
    if lat is None or lon is None or not line:
        return None, None
    for s in sets:
        if mode in s.modes and line in s.symbols and s.contains(lat, lon):
            label, path = s.symbols[line]
            return {"label": label, "image": path, "mono": s.mono_symbols}, s.credit
    return None, None


def _color(sets: tuple[Region, ...], mode: str, line: str,
           lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None or not line:
        return None
    for s in sets:
        if mode in s.modes and line in s.colors and s.contains(lat, lon):
            return s.colors[line]
    return None


def attach(conn: sqlite3.Connection, plan: TransitPlan) -> list[str]:
    """Sets leg.symbol / alternative.symbols and the line colours in place.
    Returns the credits to show."""
    sets = regions.active()
    credits: set[str] = set()
    for leg in plan.legs:
        if leg.kind == "transit":
            leg.symbol, credit = _lookup(sets, leg.mode, leg.line, leg.from_lat, leg.from_lon)
            credits.add(credit or "")
            leg.color = (_color(sets, leg.mode, leg.line, leg.from_lat, leg.from_lon)
                         or leg.color or fallback_color(leg.mode))
    for alt in plan.alternatives:
        # Only the boarding position of the first ride is known; use it for all lines of
        # the alternative (symbol sets are city-wide, so this is good enough).
        alt.symbols = []
        colors = list(alt.colors) + [None] * (len(alt.line_summary) - len(alt.colors))
        for i, (mode, line) in enumerate(alt.line_summary):
            symbol, credit = _lookup(sets, mode, line, alt.board_lat, alt.board_lon)
            alt.symbols.append(symbol)
            credits.add(credit or "")
            colors[i] = (_color(sets, mode, line, alt.board_lat, alt.board_lon)
                         or colors[i] or fallback_color(mode))
        alt.colors = colors
    return sorted(c for c in credits if c)
