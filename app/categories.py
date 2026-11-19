"""Destination categories with a symbol and OSM tag mapping.

Symbols (static/categories/<key>.svg) are own drawings: a white motif on the colour of
the category group, chosen to be understood across cultures (concrete objects and
scenes, no letters, no red cross). Overview: static/symbol-preview.html."""

from dataclasses import dataclass

ICON_DIR = "categories"
# Symbol for locations (start points): house with tree, distinct from the plain house
# used as TüBus line 2 symbol
LOCATION_ICON = f"{ICON_DIR}/location.svg"
# Destinations without a category (also on the printout)
NONE_ICON = f"{ICON_DIR}/none.svg"
# Destinations awaiting approval: replaces the category symbol in the interface only
PENDING_ICON = f"{ICON_DIR}/pending.svg"


@dataclass(frozen=True)
class Category:
    key: str
    label: str        # German msgid (English in i18n.ENGLISH)
    group: str        # German msgid of the group
    osm: tuple[str, ...] = ()  # "key=value" tags that map to this category

    @property
    def image(self) -> str:
        return f"{ICON_DIR}/{self.key}.svg"


CATEGORIES: tuple[Category, ...] = (
    # Gesundheit
    Category("hospital", "Krankenhaus", "Gesundheit",
             ("amenity=hospital", "healthcare=hospital", "amenity=clinic", "healthcare=clinic")),
    Category("doctor", "Arztpraxis", "Gesundheit",
             ("amenity=doctors", "healthcare=doctor")),
    Category("dentist", "Zahnarzt", "Gesundheit", ("amenity=dentist", "healthcare=dentist")),
    Category("pharmacy", "Apotheke", "Gesundheit",
             ("amenity=pharmacy", "healthcare=pharmacy")),
    Category("therapy", "Psychotherapie/Beratung", "Gesundheit",
             ("healthcare=psychotherapist", "healthcare=counselling", "healthcare=centre")),
    Category("physio", "Physiotherapie", "Gesundheit",
             ("healthcare=physiotherapist", "amenity=physiotherapist")),
    Category("optician", "Optiker", "Gesundheit",
             ("shop=optician", "healthcare=optometrist")),
    # Behörden
    Category("townhall", "Rathaus/Bürgeramt", "Behörden", ("amenity=townhall",)),
    Category("immigration", "Ausländerbehörde", "Behörden", ("government=immigration",)),
    Category("jobcenter", "Jobcenter/Arbeitsagentur", "Behörden",
             ("office=employment_agency", "government=employment_agency")),
    Category("police", "Polizei", "Behörden", ("amenity=police",)),
    Category("court", "Gericht", "Behörden", ("amenity=courthouse",)),
    # Bildung/Soziales
    Category("school", "Schule", "Bildung/Soziales", ("amenity=school",)),
    Category("kindergarten", "Kita", "Bildung/Soziales",
             ("amenity=kindergarten", "amenity=childcare")),
    Category("language", "Sprachkurs", "Bildung/Soziales", ("amenity=language_school",)),
    Category("counselling", "Beratungsstelle", "Bildung/Soziales",
             ("amenity=social_facility", "amenity=social_centre", "office=ngo",
              "office=association")),
    # Religion: one symbol per religion; OSM religion=* picks the category (see from_osm)
    Category("church", "Kirche", "Religion", ("religion=christian",)),
    Category("mosque", "Moschee", "Religion", ("religion=muslim",)),
    Category("synagogue", "Synagoge", "Religion", ("religion=jewish",)),
    Category("temple", "Tempel", "Religion",
             ("religion=buddhist", "religion=hindu", "religion=sikh", "religion=jain")),
    Category("worship", "Gebetsstätte", "Religion", ("amenity=place_of_worship",)),
    # Alltag
    Category("station", "Bahnhof", "Alltag",
             ("railway=station", "public_transport=station", "railway=halt")),
    Category("supermarket", "Supermarkt", "Alltag", ("shop=supermarket",)),
    Category("bank", "Bank", "Alltag", ("amenity=bank",)),
    Category("post", "Post", "Alltag", ("amenity=post_office",)),
    # Fallback
    Category("other", "Sonstiges", "Sonstiges"),
)

BY_KEY = {c.key: c for c in CATEGORIES}
GROUPS = tuple(dict.fromkeys(c.group for c in CATEGORIES))
_BY_TAG = {tag: c.key for c in CATEGORIES for tag in c.osm}


def get(key: str | None) -> Category | None:
    return BY_KEY.get(key or "")


def from_osm(osm_class: str, osm_type: str, extratags: dict | None = None) -> str:
    """Category key for a Nominatim result ('' if unknown)."""
    tags = [f"{osm_class}={osm_type}"]
    for k in ("healthcare", "government", "office", "amenity"):
        if extratags and extratags.get(k):
            tags.append(f"{k}={extratags[k]}")
    # Places of worship: the religion decides (church, mosque, ...)
    if f"{osm_class}={osm_type}" == "amenity=place_of_worship" and extratags and extratags.get("religion"):
        tags.append(f"religion={extratags['religion']}")
    # More specific tags (e.g. government=immigration) win over generic ones (office=government)
    for tag in reversed(tags):
        if tag in _BY_TAG:
            return _BY_TAG[tag]
    return ""
