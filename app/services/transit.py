"""Public transport connections via Transitous (public MOTIS 2 API), backend only.

Usage policy (https://transitous.org/api/):
- non-commercial use only
- User-Agent with app name, version and contact (config.user_agent, APP_CONTACT)
- > 720 /plan requests per day only after coordination -> daily counter + cache
- link to https://transitous.org/sources/ visibly (shown on page and printout)

API: GET /api/v6/plan (MOTIS v2.11.4 OpenAPI spec).
"""

import json
import logging
import re
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import httpx

from app import config, db
from app.i18n import (DEFAULT_DIRECTIONS_LANG, MODE_KINDS, Msg, UserError,
                      normalize_directions_lang)
from app.services.ratelimit import RateLimiter

log = logging.getLogger(__name__)

SERVICE = "transitous-plan"
SOURCES_URL = "https://transitous.org/sources/"
SETTINGS_KEY = "transit_defaults"

# UI groups -> MOTIS transit modes (see Mode schema in the OpenAPI spec)
MODE_GROUPS: dict[str, tuple[str, ...]] = {
    "bus": ("BUS",),
    "tram": ("TRAM", "SUBWAY"),
    "train": ("SUBURBAN", "REGIONAL_RAIL"),
    "long_distance": ("LONG_DISTANCE", "HIGHSPEED_RAIL", "NIGHT_RAIL", "COACH"),
    "other": ("FERRY", "FUNICULAR", "AERIAL_LIFT", "OTHER"),
}
# German msgids for the UI
MODE_GROUP_LABELS = {
    "bus": "Bus",
    "tram": "Straßenbahn/U-Bahn",
    "train": "S-Bahn/Regionalzug",
    "long_distance": "Fernverkehr (ICE/IC, Fernbus)",
    "other": "Sonstige (Fähre, Seilbahn …)",
}
# Stop sign per kind of transport (static/): bus and tram share the German "H" sign
STOP_ICONS = {"bus": "stop.svg", "tram": "stop.svg", "metro": "stop-metro.svg",
              "train": "stop-train.svg", "ferry": "stop-ferry.svg", "cable": "stop-cable.svg"}


def stop_icon(mode: str | None) -> str:
    """Static path of the stop sign for a MOTIS mode (bus sign if unknown)."""
    return STOP_ICONS.get(MODE_KINDS.get(mode or "", "bus"), "stop.svg")


WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

NICE_HEADWAYS = (5, 10, 15, 20, 30, 60, 120)


class TransitError(UserError):
    """User-facing error (translated in the UI)."""


# ---------------------------------------------------------------------------
# Settings (stored defaults, overridable per printout)
# ---------------------------------------------------------------------------

@dataclass
class TransitSettings:
    max_transfers: int = 2
    walk_start_min: int = 15
    walk_end_min: int = 15
    modes: list[str] = field(default_factory=lambda: ["bus", "tram", "train", "other"])
    wheelchair: bool = False
    weekday: int = 1          # 0 = Monday
    time: str = "09:00"       # HH:MM, local time
    auto_walk_max_min: int = 20  # automatic mode: walk if the walk takes at most this long

    LIMITS = {"max_transfers": (0, 6), "walk_start_min": (1, 30), "walk_end_min": (1, 30),
              "auto_walk_max_min": (5, 60)}

    @classmethod
    def parse(cls, raw: dict, errors: list[Msg] | None = None) -> "TransitSettings":
        """From form/query/JSON values; invalid values fall back to defaults (+ error)."""
        errors = [] if errors is None else errors
        s = cls()
        for name, (lo, hi) in cls.LIMITS.items():
            if raw.get(name) in (None, ""):
                continue
            try:
                value = int(raw[name])
                if not lo <= value <= hi:
                    raise ValueError
                setattr(s, name, value)
            except (TypeError, ValueError):
                errors.append(Msg("Ungültiger Wert für {field}: {value}", field=name,
                                  value=raw[name]))
        if "modes" in raw:
            modes = raw["modes"]
            modes = [modes] if isinstance(modes, str) else list(modes or [])
            modes = [m for m in modes if m in MODE_GROUPS]
            if modes:
                s.modes = modes
            else:
                errors.append(Msg("Bitte mindestens ein Verkehrsmittel wählen."))
        if "wheelchair" in raw:
            s.wheelchair = str(raw["wheelchair"]).lower() in ("1", "true", "on", "yes")
        if raw.get("weekday") not in (None, ""):
            try:
                weekday = int(raw["weekday"])
                if not 0 <= weekday <= 6:
                    raise ValueError
                s.weekday = weekday
            except (TypeError, ValueError):
                errors.append(Msg("Ungültiger Wert für {field}: {value}", field="weekday",
                                  value=raw["weekday"]))
        if raw.get("time"):
            try:
                s.time = datetime.strptime(str(raw["time"]).strip(), "%H:%M").strftime("%H:%M")
            except ValueError:
                errors.append(Msg("Ungültiger Wert für {field}: {value}", field="time",
                                  value=raw["time"]))
        return s

    def to_dict(self) -> dict:
        return asdict(self)

    def query_items(self) -> list[tuple[str, str]]:
        """For links (print view): marks that options were submitted explicitly."""
        items = [("transit_opts", "1"), ("max_transfers", str(self.max_transfers)),
                 ("walk_start_min", str(self.walk_start_min)),
                 ("walk_end_min", str(self.walk_end_min)),
                 ("weekday", str(self.weekday)), ("time", self.time),
                 ("auto_walk_max_min", str(self.auto_walk_max_min))]
        items += [("modes", m) for m in self.modes]
        if self.wheelchair:
            items.append(("wheelchair", "1"))
        return items

    def cache_fragment(self) -> str:
        # only what influences the Transitous request
        data = self.to_dict()
        data.pop("auto_walk_max_min", None)
        return json.dumps(data, sort_keys=True)


def load_defaults(conn: sqlite3.Connection) -> TransitSettings:
    raw = db.setting_get(conn, SETTINGS_KEY)
    return TransitSettings.parse(json.loads(raw)) if raw else TransitSettings()


def save_defaults(conn: sqlite3.Connection, settings: TransitSettings) -> None:
    db.setting_put(conn, SETTINGS_KEY, json.dumps(settings.to_dict()))


def reference_datetime(settings: TransitSettings, today: date, tz: ZoneInfo) -> datetime:
    """Next occurrence of the reference weekday (from tomorrow on) at the reference time."""
    d = today + timedelta(days=1)
    while d.weekday() != settings.weekday:
        d += timedelta(days=1)
    hh, mm = map(int, settings.time.split(":"))
    return datetime.combine(d, time(hh, mm), tz)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class TransitLeg:
    kind: str                 # "walk" | "transit"
    mode: str
    from_name: str
    to_name: str
    duration_s: int
    distance_m: float | None = None
    line: str = ""            # e.g. "5", "RE 4"
    headsign: str = ""
    color: str | None = None  # "#rrggbb"
    platform: str = ""
    wheelchair: str | None = None
    geometry: list[list[float]] = field(default_factory=list)
    from_lat: float | None = None
    from_lon: float | None = None
    to_lat: float | None = None
    to_lon: float | None = None
    symbol: dict | None = None  # {"label": ..., "image": ...}, see line_symbols.attach

    @property
    def text_color(self) -> str:
        return text_color_for(self.color)


@dataclass
class Alternative:
    line_summary: list[tuple[str, str]]  # [(mode, line), ...]
    board_stop: str
    headway_min: int | None
    duration_s: int
    board_lat: float | None = None
    board_lon: float | None = None
    symbols: list[dict | None] = field(default_factory=list)  # parallel to line_summary
    colors: list[str | None] = field(default_factory=list)    # parallel to line_summary

    @property
    def text_colors(self) -> list[str]:
        return [text_color_for(c) for c in self.colors]


@dataclass
class TransitPlan:
    profile: str
    duration_s: int
    transfers: int
    headway_min: int | None
    legs: list[TransitLeg]
    alternatives: list[Alternative] = field(default_factory=list)
    wheelchair_issue: bool = False
    reference: str = ""       # ISO datetime used for the search

    def to_dict(self) -> dict:
        legs = [asdict(leg) | {"stop_icon": f"/static/{stop_icon(leg.mode)}"} for leg in self.legs]
        return {"profile": self.profile, "legs": legs,
                "geometry": [p for leg in self.legs for p in leg.geometry]}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def decode_polyline(points: str, precision: int = 6) -> list[list[float]]:
    """Google encoded polyline -> [[lat, lon], ...]."""
    factor = 10 ** precision
    coords, lat, lon, i = [], 0, 0, 0
    while i < len(points):
        deltas = []
        for _ in range(2):
            result, shift = 0, 0
            while True:
                b = ord(points[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append([lat / factor, lon / factor])
    return coords


# First words that are not a place of their own ("Bad Urach", "St. Johann")
_PLACE_PREFIX_WORDS = {"bad", "st.", "sankt"}


def same_place_names(a: str, b: str) -> tuple[str, str]:
    """Drop the shared place from two stop names of one ride.

    German stop names start with the municipality ("Tübingen Freibad"); within one
    place it is redundant: "Tübingen Freibad" -> "Freibad". Only whole words are
    removed, and only if both names keep a rest.
    """
    wa, wb = a.split(), b.split()
    n = 0
    while n < min(len(wa), len(wb)) - 1 and wa[n] == wb[n]:
        n += 1
    if n == 0 or all(w.lower() in _PLACE_PREFIX_WORDS for w in wa[:n]):
        return a, b
    rest_a = " ".join(wa[n:]).lstrip(",-– ").strip()
    rest_b = " ".join(wb[n:]).lstrip(",-– ").strip()
    if not rest_a or not rest_b:
        return a, b
    return rest_a, rest_b


def municipality(address: str) -> str | None:
    """Place from a German address: "Straße 1, 72076 Tübingen" -> "Tübingen";
    additions in brackets are dropped ("71065 Sindelfingen (Stadt)" -> "Sindelfingen")."""
    match = re.search(r"\b\d{5}\s+([^,]+)$", (address or "").strip())
    if not match:
        return None
    return re.sub(r"\s*\([^)]*\)", "", match.group(1)).strip() or None


def common_place(address_a: str, address_b: str) -> str | None:
    """The municipality if both addresses are in the same one, else None."""
    a, b = municipality(address_a), municipality(address_b)
    return a if a and b and a.casefold() == b.casefold() else None


# Additions after the town name that stop names usually leave out
# ("Freiburg im Breisgau" -> stops "Freiburg, Paduaallee"; "Frankfurt am Main")
_PLACE_ADDITIONS = re.compile(r"\s+(?:im|am|an der|in der|ob der|bei|vor der)\s+.*$")


def strip_place(name: str, place: str | None) -> str:
    """"Tübingen Freibad" -> "Freibad" for place "Tübingen" (as on the bus displays)."""
    if not place:
        return name
    short = _PLACE_ADDITIONS.sub("", place)
    for candidate in dict.fromkeys((place, short)):   # full name first, then short form
        if name[:len(candidate)].casefold() != candidate.casefold():
            continue
        rest = name[len(candidate):]
        if rest[:1] not in (" ", ","):      # "Tübingen-Lustnau ...", "Tübinger Str."
            continue
        rest = rest.lstrip(" ,")
        if rest and not rest.startswith("("):  # "Frankfurt (Main) Hbf": part of the town
            return rest
    return name


def without_place(plan: "TransitPlan", place: str | None) -> "TransitPlan":
    """Copy of the plan with the shared municipality removed from all stop names and
    line destinations (the cached plan itself stays unchanged)."""
    if not place:
        return plan
    def short(name: str) -> str:
        return strip_place(name, place)
    legs = [replace(leg, from_name=short(leg.from_name), to_name=short(leg.to_name),
                    headsign=short(leg.headsign)) for leg in plan.legs]
    alternatives = [replace(alt, board_stop=short(alt.board_stop)) for alt in plan.alternatives]
    return replace(plan, legs=legs, alternatives=alternatives)


def _line(leg: dict) -> str:
    name = (leg.get("displayName") or leg.get("routeShortName") or leg.get("tripShortName")
            or leg.get("routeLongName") or "").strip()
    # Trains carry their trip number ("RB63 (22757)"): not needed on a printout, and it
    # would make the same line with another train look like a different connection
    return re.sub(r"\s*\(\d+\)$", "", name)


def _station(place: dict) -> str:
    """Station part of a stop: DHID 'de:08416:10700' from 'de-DELFI_de:08416:10700:0:4'
    (all platforms of a station share it), else the stop name."""
    stop_id = (place.get("stopId") or "").split("_", 1)[-1]
    parts = stop_id.split(":")
    if len(parts) >= 3 and parts[0].isalpha() and parts[1].isdigit():
        return ":".join(parts[:3])
    return (place.get("name") or "").strip()


def drop_station_transfers(legs: list[dict]) -> list[dict]:
    """Removes walks between two rides within the same station (e.g. from the bus to the
    train at 'Tübingen Hauptbahnhof'): the change of platform needs no own line."""
    result = []
    for i, leg in enumerate(legs):
        between_rides = 0 < i < len(legs) - 1 and legs[i - 1]["mode"] != "WALK" \
            and legs[i + 1]["mode"] != "WALK"
        if leg["mode"] == "WALK" and between_rides and (
                _station(leg["from"]) == _station(leg["to"])
                or (leg["from"].get("name") or "") == (leg["to"].get("name") or "")):
            continue
        result.append(leg)
    return result


def text_color_for(background: str | None) -> str:
    """Black or white, whichever has the higher WCAG contrast on the given '#rrggbb'."""
    if not background:
        return "#fff"
    def channel(hex2: str) -> float:
        c = int(hex2, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(background[i:i + 2]) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#fff"


def _color(leg: dict) -> str | None:
    """Route colour as '#rrggbb' (strictly validated: it ends up in a style attribute)."""
    color = leg.get("routeColor")
    return f"#{color}" if color and re.fullmatch(r"[0-9A-Fa-f]{6}", color) else None


def parse_leg(leg: dict) -> TransitLeg:
    geom = leg.get("legGeometry") or {}
    geometry = decode_polyline(geom.get("points", ""), int(geom.get("precision", 6))) \
        if geom.get("points") else []
    is_walk = leg["mode"] == "WALK"
    return TransitLeg(
        kind="walk" if is_walk else "transit",
        mode=leg["mode"],
        from_name=leg["from"]["name"],
        to_name=leg["to"]["name"],
        duration_s=int(leg.get("duration", 0)),
        distance_m=leg.get("distance"),
        line="" if is_walk else _line(leg),
        headsign="" if is_walk else (leg.get("headsign") or "").strip(),
        color=_color(leg),
        platform="" if is_walk else (leg["from"].get("track") or "").strip(),
        wheelchair=leg.get("wheelchairAccessible"),
        geometry=geometry,
        from_lat=leg["from"].get("lat"),
        from_lon=leg["from"].get("lon"),
        to_lat=leg["to"].get("lat"),
        to_lon=leg["to"].get("lon"),
    )


def _pattern(itinerary: dict) -> tuple:
    return tuple((leg["mode"], _line(leg), leg["from"]["name"], leg["to"]["name"])
                 for leg in itinerary["legs"] if leg["mode"] != "WALK")


def _first_transit_departure(itinerary: dict) -> datetime:
    for leg in itinerary["legs"]:
        if leg["mode"] != "WALK":
            return datetime.fromisoformat(leg["startTime"].replace("Z", "+00:00"))
    return datetime.fromisoformat(itinerary["startTime"].replace("Z", "+00:00"))


def headway_minutes(departures: list[datetime]) -> int | None:
    """Typical interval between departures, rounded to a 'nice' value."""
    times = sorted(set(departures))
    if len(times) < 2:
        return None
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
    median = statistics.median(gaps)
    if median <= 0:
        return None
    return min(NICE_HEADWAYS, key=lambda n: abs(n - median))


SHORT_RIDE_S = 180   # rides shorter than this are ranked down (see summarize)


def short_rides(itinerary: dict) -> int:
    """Number of rides shorter than SHORT_RIDE_S in an itinerary."""
    return sum(1 for leg in itinerary.get("legs", [])
               if leg["mode"] != "WALK" and leg.get("duration", SHORT_RIDE_S) < SHORT_RIDE_S)


def summarize(data: dict, wheelchair: bool, reference: str = "") -> TransitPlan:
    itineraries = [it for it in data.get("itineraries") or [] if _pattern(it)]
    if not itineraries:
        raise TransitError(Msg("Keine ÖPNV-Verbindung gefunden. Optionen (Fußweg, Umstiege, "
                               "Verkehrsmittel) lockern oder andere Uhrzeit wählen."))

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for it in itineraries:
        groups[_pattern(it)].append(it)

    def rank(item):
        _pattern_key, its = item
        # A ride of 1-2 minutes (e.g. one stop, then walking on) costs a change and is
        # easily missed: it counts like an extra transfer
        short = short_rides(its[0])
        return (min(i["transfers"] for i in its) + short,
                statistics.median(i["duration"] for i in its),
                -len(its))

    ranked = sorted(groups.items(), key=rank)
    best_key, best_its = ranked[0]
    # Representative: the most common duration variant (first occurrence)
    rep = min(best_its, key=lambda i: i["duration"])
    legs = [parse_leg(leg) for leg in drop_station_transfers(rep["legs"])]

    alternatives = []
    for key, its in ranked[1:3]:
        rides = [leg for leg in its[0]["legs"] if leg["mode"] != "WALK"]
        first = rides[0]
        alternatives.append(Alternative(
            line_summary=[(mode, line) for mode, line, _f, _t in key],
            colors=[_color(leg) for leg in rides],
            board_stop=first["from"]["name"],
            board_lat=first["from"].get("lat"),
            board_lon=first["from"].get("lon"),
            headway_min=headway_minutes([_first_transit_departure(i) for i in its]),
            duration_s=int(statistics.median(i["duration"] for i in its)),
        ))

    return TransitPlan(
        profile="transit",
        duration_s=int(rep["duration"]),
        transfers=int(rep["transfers"]),
        headway_min=headway_minutes([_first_transit_departure(i) for i in best_its]),
        legs=legs,
        alternatives=alternatives,
        wheelchair_issue=wheelchair and any(
            leg.kind == "transit" and leg.wheelchair != "ACCESSIBLE" for leg in legs),
        reference=reference,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return str(body.get("error") or body.get("message") or body)[:200]
    except ValueError:
        return resp.text[:200]


class TransitousClient:
    def __init__(self, base_url: str, user_agent: str, has_contact: bool,
                 daily_limit: int = 300, cache_days: int = 3, timezone: str = "Europe/Berlin",
                 rate_limiter: RateLimiter | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.has_contact = has_contact
        self.daily_limit = daily_limit
        self.cache_days = cache_days
        self.tz = ZoneInfo(timezone)
        self.rate_limiter = rate_limiter or RateLimiter(1.0)
        self._http = httpx.Client(transport=transport, timeout=timeout,
                                  headers={"User-Agent": user_agent})

    def plan(self, conn: sqlite3.Connection, start: tuple[float, float],
             end: tuple[float, float], settings: TransitSettings,
             language: str = DEFAULT_DIRECTIONS_LANG,
             today: date | None = None) -> tuple[TransitPlan, bool]:
        """start/end as (lat, lon). Returns (plan, from_cache)."""
        language = normalize_directions_lang(language)
        ref = reference_datetime(settings, today or date.today(), self.tz)
        key = (f"motis|{start[0]:.5f},{start[1]:.5f}|{end[0]:.5f},{end[1]:.5f}|{language}|"
               f"{settings.cache_fragment()}")
        cached = db.cache_get(conn, key, self.cache_days)
        if cached is not None:
            payload = json.loads(cached)
            return summarize(payload["data"], settings.wheelchair, payload["reference"]), True

        if not self.has_contact:
            raise TransitError(Msg("Für ÖPNV-Abfragen muss ein Kontakt konfiguriert sein "
                                   "(APP_CONTACT in .env), so verlangt es Transitous."))
        if db.usage_today(conn, SERVICE) >= self.daily_limit:
            raise TransitError(Msg("Tageslimit für ÖPNV-Abfragen erreicht ({limit}). "
                                   "Bitte morgen erneut versuchen.", limit=self.daily_limit))

        modes = [m for group in settings.modes for m in MODE_GROUPS[group]]
        params = {
            "fromPlace": f"{start[0]},{start[1]}",
            "toPlace": f"{end[0]},{end[1]}",
            "time": ref.isoformat(),
            "maxTransfers": settings.max_transfers,
            "maxPreTransitTime": settings.walk_start_min * 60,
            "maxPostTransitTime": settings.walk_end_min * 60,
            "transitModes": ",".join(modes),
            # transit only; otherwise slower transit options would be cut off by walking
            "directModes": "",
            "pedestrianProfile": "WHEELCHAIR" if settings.wheelchair else "FOOT",
            "searchWindow": 7200,
            "numItineraries": 10,
            "detailedLegs": "true",
            "language": "uk" if language == "ua" else ("el" if language == "gr" else language),
        }
        self.rate_limiter.wait()
        db.usage_increment(conn, SERVICE)
        try:
            resp = self._http.get(f"{self.base_url}/api/v6/plan", params=params)
        except httpx.HTTPError as exc:
            log.warning("Transitous request failed: %s", exc)
            raise TransitError(Msg("Der ÖPNV-Dienst ist gerade nicht erreichbar.")) from exc
        if resp.status_code != 200:
            log.warning("Transitous error %s: %s", resp.status_code, _error_detail(resp))
            raise TransitError(Msg("ÖPNV-Abfrage fehlgeschlagen: {detail}",
                                   detail=f"HTTP {resp.status_code} {_error_detail(resp)}"))
        try:
            data = resp.json()
            plan = summarize(data, settings.wheelchair, ref.isoformat())
        except TransitError:
            raise
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            log.warning("Unexpected Transitous response: %s", exc)
            raise TransitError(Msg("Die Antwort des ÖPNV-Dienstes war unerwartet.")) from exc

        db.cache_put(conn, key, json.dumps({"data": data, "reference": ref.isoformat()}))
        return plan, False


@lru_cache(maxsize=1)
def get_transit() -> TransitousClient:
    """Process-wide client, so the rate limit applies across all requests."""
    return TransitousClient(
        base_url=config.transitous_base_url(),
        user_agent=config.user_agent(),
        has_contact=bool(config.contact()),
        daily_limit=config.transitous_daily_limit(),
        cache_days=config.transit_cache_days(),
        timezone=config.timezone(),
    )
