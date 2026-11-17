"""Map-provider links for a destination and their QR codes (generated locally with segno)."""

from dataclasses import dataclass
from urllib.parse import quote, urlencode

import segno

from app.db import Destination


@dataclass
class MapLink:
    key: str     # "google" | "osm" | "apple"
    label: str   # provider name (already in the directions language)
    url: str
    svg: str     # inline SVG, size controlled via CSS


def google_url(dest: Destination) -> str:
    """Verified link if stored, otherwise a Maps URL search (no API key needed)."""
    if dest.google_maps_url:
        return dest.google_maps_url
    query = f"{dest.name}, {dest.address}"
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query},
                                                             quote_via=quote)


def osm_url(dest: Destination) -> str:
    lat, lon = f"{dest.lat:.6f}", f"{dest.lon:.6f}"
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"


def apple_url(dest: Destination) -> str:
    # Unified Maps URLs (iOS 18.4+): /place with coordinate and custom name
    return "https://maps.apple.com/place?" + urlencode(
        {"coordinate": f"{dest.lat:.6f},{dest.lon:.6f}", "name": dest.name}, quote_via=quote
    )


def qr_svg(data: str) -> str:
    return segno.make(data, error="m", micro=False).svg_inline(
        scale=1, border=2, omitsize=True, dark="#000", light="#fff"
    )


def map_links(dest: Destination, apple_label: str) -> list[MapLink]:
    links = [
        ("google", "Google Maps", google_url(dest)),
        ("osm", "OpenStreetMap", osm_url(dest)),
        ("apple", apple_label, apple_url(dest)),
    ]
    return [MapLink(key, label, url, qr_svg(url)) for key, label, url in links]
