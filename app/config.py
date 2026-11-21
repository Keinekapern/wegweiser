import os
from pathlib import Path

APP_NAME = "Wegweiser"
APP_VERSION = "0.1.0"


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "data/wegweiser.sqlite"))


def nominatim_base_url() -> str:
    return os.environ.get("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")


def nominatim_countrycodes() -> str:
    return os.environ.get("NOMINATIM_COUNTRYCODES", "de").strip()


def geocode_cache_days() -> int:
    return int(os.environ.get("GEOCODE_CACHE_DAYS", "30"))


def contact() -> str:
    """Contact for the User-Agent (required by Transitous). NOMINATIM_CONTACT is the old name."""
    return (os.environ.get("APP_CONTACT") or os.environ.get("NOMINATIM_CONTACT") or "").strip()


def timezone() -> str:
    return os.environ.get("TIMEZONE", "Europe/Berlin")


def transitous_base_url() -> str:
    return os.environ.get("TRANSITOUS_BASE_URL", "https://api.transitous.org").rstrip("/")


def transitous_daily_limit() -> int:
    return int(os.environ.get("TRANSITOUS_DAILY_LIMIT", "300"))


def transit_cache_days() -> int:
    return int(os.environ.get("TRANSIT_CACHE_DAYS", "3"))


def user_agent() -> str:
    contact_ = contact()
    base = f"{APP_NAME}/{APP_VERSION} (private self-hosted directions tool"
    return f"{base}; {contact_})" if contact_ else f"{base})"


def ors_api_key() -> str:
    return os.environ.get("ORS_API_KEY", "").strip()


def ors_base_url() -> str:
    return os.environ.get("ORS_BASE_URL", "https://api.heigit.org/openrouteservice").rstrip("/")


def ors_daily_limit() -> int:
    return int(os.environ.get("ORS_DAILY_LIMIT", "1800"))


def route_cache_days() -> int:
    return int(os.environ.get("ROUTE_CACHE_DAYS", "7"))


# Attribution shown on page and printout. Defaults fit the public services;
# a self-hosted MOTIS/ORS must name its own data source (e.g. NVBW, ODbL).
def transit_attribution() -> str:
    return os.environ.get("TRANSIT_ATTRIBUTION", "").strip() or "Transitous"


def transit_attribution_url() -> str:
    return os.environ.get("TRANSIT_ATTRIBUTION_URL", "").strip() or "https://transitous.org/sources/"


def route_attribution() -> str:
    return os.environ.get("ROUTE_ATTRIBUTION", "").strip() or "openrouteservice.org (HeiGIT)"


# Map tiles, loaded by the browser. Attribution is HTML and must stay visible.
def tile_url() -> str:
    return os.environ.get("TILE_URL", "").strip() or "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def tile_attribution() -> str:
    return (os.environ.get("TILE_ATTRIBUTION", "").strip()
            or '<a href="https://www.openstreetmap.org/copyright">&copy; OpenStreetMap</a>')


def tile_max_zoom() -> int:
    return int(os.environ.get("TILE_MAX_ZOOM", "").strip() or "19")


# Access control: "admin" (default) = anyone may use it and propose destinations, admins
# approve and edit; "off" = no login, everyone may change everything (own PC or a small
# trusted network only). See README, "Admins und Rechte".
AUTH_MODES = ("off", "admin")


def auth_mode() -> str:
    mode = os.environ.get("AUTH_MODE", "").strip().lower() or "admin"
    if mode not in AUTH_MODES:
        raise ValueError(f"AUTH_MODE must be one of {', '.join(AUTH_MODES)}, not {mode!r}")
    return mode


def tunnel_configured() -> bool:
    return bool(os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip())
