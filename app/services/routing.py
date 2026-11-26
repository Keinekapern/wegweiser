"""Car and foot routes via openrouteservice (HeiGIT), called only from the backend.

- Base URL: https://api.heigit.org/openrouteservice (api.openrouteservice.org was
  shut down in Nov 2026, see ask.openrouteservice.org announcement #7912)
- API key only server-side (Authorization header)
- Free plan: ~2000 directions/day, 40/min -> daily counter + rate limiter + cache
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import httpx

from app import config, db
from app.i18n import (DEFAULT_DIRECTIONS_LANG, Msg, UserError, normalize_directions_lang,
                      ors_language)
from app.services.ratelimit import RateLimiter

log = logging.getLogger(__name__)

SERVICE = "ors-directions"
ATTRIBUTION = "Route: openrouteservice.org (HeiGIT) | Daten © OpenStreetMap-Mitwirkende"

# profile -> UI label (German msgid)
PROFILES = {
    "driving-car": "Auto",          # not offered in the UI any more, kept for old links
    "foot-walking": "Zu Fuß",
}


class RoutingError(UserError):
    """User-facing error (translated in the UI)."""


@dataclass
class Step:
    instruction: str
    distance_m: float
    duration_s: float
    type: int | None = None         # ORS instruction type (used for generated languages)
    name: str = ""                  # street name
    exit_number: int | None = None  # roundabouts


@dataclass
class Route:
    profile: str
    distance_m: float
    duration_s: float
    geometry: list[list[float]]  # [[lat, lon], ...] for Leaflet
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_route(profile: str, data: dict) -> Route:
    feature = data["features"][0]
    props = feature["properties"]
    summary = props.get("summary") or {}
    steps = [
        Step(s.get("instruction", ""), float(s.get("distance", 0)), float(s.get("duration", 0)),
             type=s.get("type"), name=s.get("name") or "", exit_number=s.get("exit_number"))
        for seg in props.get("segments") or []
        for s in seg.get("steps") or []
    ]
    geometry = [[lat, lon] for lon, lat, *_ in feature["geometry"]["coordinates"]]
    return Route(
        profile=profile,
        distance_m=float(summary.get("distance", 0)),
        duration_s=float(summary.get("duration", 0)),
        geometry=geometry,
        steps=steps,
    )


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error")
        if isinstance(err, dict):
            return f"{err.get('message', '')} (Code {err.get('code', '?')})"
        return str(err or resp.text[:200])
    except ValueError:
        return resp.text[:200]


HOSTED_ORS = ("api.heigit.org", "openrouteservice.org")


class OrsClient:
    def __init__(self, base_url: str, api_key: str, daily_limit: int = 1800,
                 cache_days: int = 7, rate_limiter: RateLimiter | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # Public HeiGIT API needs a key and has a per-minute limit; a self-hosted
        # instance (ORS_BASE_URL pointing elsewhere) usually has neither.
        self.hosted = any(h in self.base_url for h in HOSTED_ORS)
        self.daily_limit = daily_limit
        self.cache_days = cache_days
        # Free plan: 40 directions/minute
        self.rate_limiter = rate_limiter or (RateLimiter(1.5) if self.hosted else None)
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": config.user_agent(), "Accept": "application/geo+json"},
        )

    @staticmethod
    def _cache_key(profile: str, start: tuple[float, float], end: tuple[float, float],
                   language: str) -> str:
        # 5 decimals ≈ 1 m
        return (f"ors|{profile}|{language}|{start[0]:.5f},{start[1]:.5f}|"
                f"{end[0]:.5f},{end[1]:.5f}")

    def route(self, conn: sqlite3.Connection, profile: str,
              start: tuple[float, float], end: tuple[float, float],
              language: str = DEFAULT_DIRECTIONS_LANG) -> tuple[Route, bool]:
        """start/end as (lat, lon). Returns (route, from_cache)."""
        if profile not in PROFILES:
            raise RoutingError(Msg("Unbekanntes Verkehrsmittel: {profile}", profile=profile))
        # Languages ORS does not support: request English data, texts are generated later
        language = ors_language(normalize_directions_lang(language))

        key = self._cache_key(profile, start, end, language)
        cached = db.cache_get(conn, key, self.cache_days)
        if cached is not None:
            return parse_route(profile, json.loads(cached)), True

        if not self.api_key and self.hosted:
            raise RoutingError(Msg("Kein openrouteservice-API-Key konfiguriert (ORS_API_KEY in .env)."))
        if db.usage_today(conn, SERVICE) >= self.daily_limit:
            raise RoutingError(Msg(
                "Tageslimit für Routenberechnungen erreicht ({limit}). "
                "Bitte morgen erneut versuchen.", limit=self.daily_limit
            ))

        body = {
            # ORS expects [lon, lat]
            "coordinates": [[start[1], start[0]], [end[1], end[0]]],
            "language": language,
            "units": "m",
            "instructions": True,
            "radiuses": [350, 350],
        }
        if self.rate_limiter:
            self.rate_limiter.wait()
        db.usage_increment(conn, SERVICE)
        try:
            resp = self._http.post(
                f"{self.base_url}/v2/directions/{profile}/geojson",
                json=body,
                headers={"Authorization": self.api_key} if self.api_key else {},
            )
        except httpx.HTTPError as exc:
            log.warning("ORS request failed: %s", exc)
            raise RoutingError(Msg("Der Routing-Dienst ist gerade nicht erreichbar.")) from exc

        if resp.status_code in (401, 403):
            log.warning("ORS auth/quota error %s: %s", resp.status_code, _error_message(resp))
            raise RoutingError(Msg(
                "openrouteservice hat die Anfrage abgelehnt (API-Key ungültig oder Kontingent "
                "erschöpft): {detail}", detail=_error_message(resp)
            ))
        if resp.status_code == 429:
            raise RoutingError(Msg("Zu viele Routenanfragen. Bitte kurz warten und erneut versuchen."))
        if resp.status_code != 200:
            log.warning("ORS error %s: %s", resp.status_code, _error_message(resp))
            raise RoutingError(Msg("Route konnte nicht berechnet werden: {detail}",
                                   detail=_error_message(resp)))

        try:
            data = resp.json()
            route = parse_route(profile, data)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            log.warning("Unexpected ORS response: %s", exc)
            raise RoutingError(Msg("Die Antwort des Routing-Dienstes war unerwartet.")) from exc

        db.cache_put(conn, key, json.dumps(data))
        return route, False


@lru_cache(maxsize=1)
def get_router() -> OrsClient:
    """Process-wide client, so the rate limit applies across all requests."""
    return OrsClient(
        base_url=config.ors_base_url(),
        api_key=config.ors_api_key(),
        daily_limit=config.ors_daily_limit(),
        cache_days=config.route_cache_days(),
    )
