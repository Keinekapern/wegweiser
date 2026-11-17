"""Nominatim geocoding, called only from the backend.

Usage policy: https://operations.osmfoundation.org/policies/nominatim/
- max. 1 request per second (enforced globally by RateLimiter)
- identifying User-Agent (see config.user_agent)
- only user-triggered searches, no autocomplete
- results cached in SQLite (api_cache)
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import httpx

from app import categories, config, db
from app.i18n import DIRECTIONS_LANGUAGES, Msg, UserError
from app.services.ratelimit import RateLimiter

log = logging.getLogger(__name__)

ATTRIBUTION = "Suchdaten © OpenStreetMap-Mitwirkende (ODbL), Geocoding: Nominatim"
RESULT_LIMIT = 8


class GeocodingError(UserError):
    """User-facing error (translated in the UI)."""


@dataclass
class Candidate:
    name: str
    address: str
    display_name: str
    lat: float
    lon: float
    phone: str
    website: str
    opening_hours: str
    osm_type: str | None
    osm_id: int | None
    category: str
    type: str
    dest_category: str = ""   # our category key (app/categories.py)
    names: dict = field(default_factory=dict)  # translated names {directions lang: name}

    def to_dict(self) -> dict:
        return asdict(self)


def _first(mapping: dict, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value:
            return str(value).strip()
    return ""


def format_address(addr: dict) -> str:
    """'Straße Nr., PLZ Ort' from Nominatim addressdetails."""
    street = " ".join(p for p in (_first(addr, "road", "pedestrian", "footway", "square"),
                                  _first(addr, "house_number")) if p)
    city = _first(addr, "city", "town", "village", "municipality", "hamlet")
    district = _first(addr, "suburb", "city_district")
    if district and district != city and not street:
        city = f"{city} ({district})" if city else district
    place = " ".join(p for p in (_first(addr, "postcode"), city) if p)
    return ", ".join(p for p in (street, place) if p)


# Directions language code -> OSM name:* suffixes (OSM uses ISO 639-1, ORS partly not)
_OSM_NAME_LANGS = {"gr": ("el",), "ua": ("uk",), "nb": ("nb", "no"), "zh": ("zh", "zh-Hans")}


def translated_names(namedetails: dict, original: str) -> dict[str, str]:
    """{directions lang: name} from OSM name:<lang> tags, without copies of the original."""
    names = {}
    for lang in DIRECTIONS_LANGUAGES:
        if lang == "de":
            continue
        for suffix in _OSM_NAME_LANGS.get(lang, (lang,)):
            value = (namedetails.get(f"name:{suffix}") or "").strip()
            if value and value != original:
                names[lang] = value
                break
    return names


def parse_result(item: dict) -> Candidate:
    addr = item.get("address") or {}
    tags = item.get("extratags") or {}
    names = item.get("namedetails") or {}
    address = format_address(addr) or item.get("display_name", "")
    name = _first(item, "name") or _first(names, "name") or address
    osm_type = item.get("osm_type")
    if osm_type not in ("node", "way", "relation"):
        osm_type = None
    return Candidate(
        name=name,
        address=address,
        display_name=item.get("display_name", ""),
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        phone=_first(tags, "phone", "contact:phone"),
        website=_first(tags, "website", "contact:website", "url"),
        opening_hours=_first(tags, "opening_hours"),
        osm_type=osm_type,
        osm_id=int(item["osm_id"]) if item.get("osm_id") and osm_type else None,
        category=_first(item, "category", "class"),
        type=_first(item, "type"),
        dest_category=categories.from_osm(_first(item, "category", "class"),
                                          _first(item, "type"), tags),
        names=translated_names(names, name),
    )


def normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


class NominatimClient:
    def __init__(self, base_url: str, user_agent: str, countrycodes: str = "",
                 cache_days: int = 30, rate_limiter: RateLimiter | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.countrycodes = countrycodes
        self.cache_days = cache_days
        self.rate_limiter = rate_limiter or RateLimiter(1.0)
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept-Language": "de"},
        )

    def _params(self, query: str) -> dict:
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "limit": RESULT_LIMIT,
            "accept-language": "de",
        }
        if self.countrycodes:
            params["countrycodes"] = self.countrycodes
        return params

    def _cache_key(self, query: str) -> str:
        return f"search|{self.countrycodes}|{RESULT_LIMIT}|{normalize_query(query)}"

    def search(self, conn: sqlite3.Connection, query: str) -> tuple[list[Candidate], bool]:
        """Returns (candidates, from_cache)."""
        key = self._cache_key(query)
        cached = db.cache_get(conn, key, self.cache_days)
        if cached is not None:
            return self._parse(json.loads(cached)), True

        self.rate_limiter.wait()
        db.usage_increment(conn, "nominatim")
        try:
            resp = self._http.get(f"{self.base_url}/search", params=self._params(query))
        except httpx.HTTPError as exc:
            log.warning("Nominatim request failed: %s", exc)
            raise GeocodingError(Msg("Die Adresssuche ist gerade nicht erreichbar.")) from exc

        if resp.status_code in (403, 429):
            log.warning("Nominatim refused request: HTTP %s", resp.status_code)
            raise GeocodingError(Msg(
                "Nominatim hat die Anfrage abgelehnt (zu viele Anfragen oder gesperrt). "
                "Bitte später erneut versuchen."
            ))
        if resp.status_code != 200:
            log.warning("Nominatim returned HTTP %s", resp.status_code)
            raise GeocodingError(Msg("Die Adresssuche hat einen Fehler gemeldet (HTTP {status}).",
                                     status=resp.status_code))

        try:
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("expected list")
            candidates = self._parse(data)
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("Unexpected Nominatim response: %s", exc)
            raise GeocodingError(Msg("Die Antwort der Adresssuche war unerwartet.")) from exc

        db.cache_put(conn, key, json.dumps(data))
        return candidates, False

    @staticmethod
    def _parse(data: list) -> list[Candidate]:
        return [parse_result(item) for item in data]


@lru_cache(maxsize=1)
def get_geocoder() -> NominatimClient:
    """Process-wide client, so the rate limit applies across all requests."""
    return NominatimClient(
        base_url=config.nominatim_base_url(),
        user_agent=config.user_agent(),
        countrycodes=config.nominatim_countrycodes(),
        cache_days=config.geocode_cache_days(),
    )
