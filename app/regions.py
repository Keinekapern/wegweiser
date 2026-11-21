"""Regional add-ons: data that only applies to one city or transport network.

Each add-on is a folder app/regions/<key>/ with a region.json and its files, e.g.
TüBus Tübingen: pictograms behind the line numbers and the official line colours. They
are loaded at start; leave an add-on out by deleting its folder or with
REGIONS=<key>,<key> in .env (REGIONS=none: no add-ons; not set: all installed ones).

region.json:
    {
      "name": "TüBus Tübingen",
      "about": "where the data comes from",
      "area": {"min_lat": 48.45, "min_lon": 8.93, "max_lat": 48.59, "max_lon": 9.15},
      "modes": ["BUS"],                     MOTIS modes the lines belong to
      "mono_symbols": true,                 symbols are single-colour (drawn in the text colour)
      "credit": "",                         attribution for the printout, if the files need one
      "lines": {"1": {"color": "#e7000e", "symbol": "cat.svg", "label": "Katze"}, ...}
    }

A transit leg uses a line's entry if its boarding stop lies inside the area and its mode
is listed. Symbols are served under /regions/<key>/symbols/.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app import config

log = logging.getLogger(__name__)

REGIONS_DIR = Path(__file__).parent / "regions"
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass
class Region:
    key: str
    name: str
    modes: set[str]
    bbox: tuple[float, float, float, float]          # min_lat, min_lon, max_lat, max_lon
    credit: str = ""
    about: str = ""
    mono_symbols: bool = True
    symbols: dict[str, tuple[str, str]] = field(default_factory=dict)   # line -> (label, path)
    colors: dict[str, str] = field(default_factory=dict)                # line -> "#rrggbb"

    def contains(self, lat: float, lon: float) -> bool:
        return self.bbox[0] <= lat <= self.bbox[2] and self.bbox[1] <= lon <= self.bbox[3]


def load(directory: Path) -> Region:
    """One add-on; raises ValueError with a readable message if region.json is wrong."""
    data = json.loads((directory / "region.json").read_text(encoding="utf-8"))
    try:
        a = data["area"]
        region = Region(
            key=directory.name, name=str(data["name"]),
            modes={str(m) for m in data.get("modes", ["BUS"])},
            bbox=(float(a["min_lat"]), float(a["min_lon"]), float(a["max_lat"]), float(a["max_lon"])),
            credit=str(data.get("credit", "")), about=str(data.get("about", "")),
            mono_symbols=bool(data.get("mono_symbols", True)))
        for line, entry in data.get("lines", {}).items():
            if "color" in entry:
                if not _HEX.fullmatch(entry["color"]):
                    raise ValueError(f"line {line}: color must be #rrggbb")
                region.colors[str(line)] = entry["color"].lower()
            if "symbol" in entry:
                path = f"{directory.name}/symbols/{entry['symbol']}"
                if not (REGIONS_DIR / path).is_file():
                    raise ValueError(f"line {line}: symbols/{entry['symbol']} is missing")
                region.symbols[str(line)] = (str(entry.get("label", line)), path)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing or wrong field: {exc}") from exc
    return region


def installed() -> list[str]:
    if not REGIONS_DIR.is_dir():
        return []
    return sorted(d.name for d in REGIONS_DIR.iterdir() if (d / "region.json").is_file())


@lru_cache(maxsize=4)
def _active(selection: str) -> tuple[Region, ...]:
    keys = installed() if selection == "" else (
        [] if selection == "none" else [k.strip() for k in selection.split(",") if k.strip()])
    regions = []
    for key in keys:
        if key not in installed():
            log.warning("REGIONS: add-on %r is not installed (app/regions/%s)", key, key)
            continue
        try:
            regions.append(load(REGIONS_DIR / key))
        except (ValueError, json.JSONDecodeError) as exc:
            log.error("Regional add-on %s not loaded: %s", key, exc)
    return tuple(regions)


def active() -> tuple[Region, ...]:
    """The add-ons in use (REGIONS in .env), loaded once."""
    return _active(config.regions())
