"""Form validation helpers. Errors are Msg objects, translated when rendered."""

import re
from urllib.parse import urlsplit

from app.i18n import Msg

GOOGLE_HOST = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")
GOOGLE_SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl"}


def parse_coordinate(raw: str, label: str, limit: float, errors: list[Msg]) -> float | None:
    """Accept both '48.1' and German '48,1'."""
    try:
        value = float(str(raw).strip().replace(",", "."))
    except ValueError:
        errors.append(Msg("{label} ist keine gültige Zahl.", label=Msg(label)))
        return None
    if not -limit <= value <= limit:
        errors.append(Msg("{label} muss zwischen {min} und {max} liegen.",
                          label=Msg(label), min=f"-{limit:g}", max=f"{limit:g}"))
        return None
    return value


def required_text(raw: str, label: str, errors: list[Msg]) -> str:
    value = raw.strip()
    if not value:
        errors.append(Msg("{label} darf nicht leer sein.", label=Msg(label)))
    return value


def optional_url(raw: str, label: str, errors: list[Msg]) -> str:
    value = raw.strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        errors.append(Msg("{label} ist keine gültige Web-Adresse.", label=Msg(label)))
    return value


def optional_google_maps_url(raw: str, errors: list[Msg]) -> str:
    value = raw.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (GOOGLE_HOST.search(host) or host in GOOGLE_SHORT_HOSTS):
        errors.append(Msg("Google-Maps-Link muss mit https:// beginnen und auf google.… "
                          "oder maps.app.goo.gl zeigen."))
    return value


def optional_osm_ref(osm_type: str, osm_id: str) -> tuple[str | None, int | None]:
    """Hidden fields from the OSM search; silently dropped if malformed."""
    osm_type = osm_type.strip()
    if osm_type not in ("node", "way", "relation"):
        return None, None
    try:
        return osm_type, int(osm_id)
    except ValueError:
        return None, None


_NUMBER = r"-?\d{1,3}(?:[.,]\d+)?"


def parse_coordinates(raw: str, errors: list[Msg]) -> tuple[float | None, float | None]:
    """'48.690351, 9.032999' (as copied from Google Maps/OSM) -> (lat, lon).

    Also accepts '48.690351,9.032999', '48.690351 9.032999', '48.690351; 9.032999'
    and German decimal commas when separated by space/semicolon ('48,69 9,03').
    """
    text = raw.strip().strip("()[]")
    if not text:
        errors.append(Msg("{label} darf nicht leer sein.", label=Msg("Koordinaten")))
        return None, None
    if ";" in text:
        parts = text.split(";")
    elif "." in text:
        parts = text.split(",") if "," in text else text.split()
    else:
        parts = text.split()          # decimal commas: numbers separated by whitespace
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) != 2 or not all(re.fullmatch(_NUMBER, p) for p in parts):
        errors.append(Msg("Koordinaten nicht erkannt. Bitte im Format „48.690351, 9.032999“ "
                          "eingeben (Breite, Länge)."))
        return None, None
    lat = parse_coordinate(parts[0], "Breitengrad", 90, errors)
    lon = parse_coordinate(parts[1], "Längengrad", 180, errors)
    return lat, lon


def coordinates_from_form(form, errors: list[Msg]) -> tuple[float | None, float | None]:
    """Combined field 'coords', or the separate 'lat'/'lon' fields (older clients)."""
    coords = str(form.get("coords") or "").strip()
    if coords or not (form.get("lat") or form.get("lon")):
        return parse_coordinates(coords, errors)
    return (parse_coordinate(str(form.get("lat", "")), "Breitengrad", 90, errors),
            parse_coordinate(str(form.get("lon", "")), "Längengrad", 180, errors))


def normalize_phone(raw: str, country_code: str = "49") -> str:
    """Bring a phone number into international format, keeping its grouping.

    '07071/29-0' -> '+49 7071 29-0', '0049 7071 290' -> '+49 7071 290',
    '+49 (0)7071 290' -> '+49 7071 290', '(07071) 29 0' -> '+49 7071 29 0'.
    Returns '' for empty input; does not validate (see optional_phone).
    """
    text = raw.strip()
    if not text:
        return ""
    text = text.replace("/", " ").replace("(0)", " ")
    text = re.sub(r"[()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("00"):
        text = "+" + text[2:].lstrip()
    elif text.startswith("0"):
        text = f"+{country_code} " + text[1:].lstrip()
    elif not text.startswith("+") and text[:1].isdigit():
        # local number without area code: cannot be completed reliably, keep it
        return text
    # "+497071..." -> "+49 7071..." (space after the country code for readability)
    if text.startswith(f"+{country_code}") and not text.startswith(f"+{country_code} "):
        text = f"+{country_code} " + text[len(country_code) + 1:].lstrip()
    return re.sub(r"\s+", " ", text).strip()


def optional_phone(raw: str, errors: list[Msg]) -> str:
    phone = normalize_phone(raw)
    if phone and not re.fullmatch(r"\+?[0-9][0-9 \-]{4,}", phone):
        errors.append(Msg("Telefonnummer „{phone}“ ist ungültig – bitte mit Vorwahl eingeben.",
                          phone=raw.strip()))
    return phone
