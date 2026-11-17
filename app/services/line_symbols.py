"""Pictograms next to line numbers (e.g. TüBus Tübingen: line 1 = cat).

A symbol set covers an area (bounding box) and some modes; a transit leg gets the
symbol if its boarding stop lies inside the area and the set has its line number.
"""

import sqlite3

from app import db
from app.services.transit import TransitPlan


def _lookup(sets: list[db.LineSymbolSet], mode: str, line: str,
            lat: float | None, lon: float | None) -> tuple[dict | None, str | None]:
    if lat is None or lon is None or not line:
        return None, None
    for s in sets:
        if mode in s.modes and line in s.symbols and s.contains(lat, lon):
            label, image = s.symbols[line]
            return {"label": label, "image": image}, s.credit
    return None, None


def attach(conn: sqlite3.Connection, plan: TransitPlan) -> list[str]:
    """Sets leg.symbol / alternative.symbols in place. Returns the credits to show."""
    sets = db.list_line_symbol_sets(conn)
    credits: set[str] = set()
    for leg in plan.legs:
        if leg.kind == "transit":
            leg.symbol, credit = _lookup(sets, leg.mode, leg.line, leg.from_lat, leg.from_lon)
            credits.add(credit or "")
    for alt in plan.alternatives:
        # Only the boarding position of the first ride is known; use it for all lines of
        # the alternative (symbol sets are city-wide, so this is good enough).
        alt.symbols = []
        for mode, line in alt.line_summary:
            symbol, credit = _lookup(sets, mode, line, alt.board_lat, alt.board_lon)
            alt.symbols.append(symbol)
            credits.add(credit or "")
    return sorted(c for c in credits if c)
