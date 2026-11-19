from pathlib import Path

import pytest

from app import categories
from app.i18n import ENGLISH
from app.services.geocoding import parse_result
from tests.conftest import SAMPLE_RESULT

STATIC = Path(__file__).parent.parent / "app" / "static"


def test_every_category_has_icon_and_translation():
    for c in categories.CATEGORIES:
        assert (STATIC / c.image).is_file(), c.key
        assert c.label in ENGLISH and c.group in ENGLISH


@pytest.mark.parametrize("cls,typ,extra,expected", [
    ("amenity", "pharmacy", {}, "pharmacy"),
    ("amenity", "hospital", {}, "hospital"),
    ("amenity", "doctors", {"healthcare": "doctor"}, "doctor"),
    ("office", "government", {"government": "immigration"}, "immigration"),
    ("healthcare", "psychotherapist", {}, "therapy"),
    ("shop", "bakery", {}, ""),
    # places of worship: the religion picks the symbol
    ("amenity", "place_of_worship", {"religion": "christian"}, "church"),
    ("amenity", "place_of_worship", {"religion": "muslim"}, "mosque"),
    ("amenity", "place_of_worship", {"religion": "jewish"}, "synagogue"),
    ("amenity", "place_of_worship", {"religion": "buddhist"}, "temple"),
    ("amenity", "place_of_worship", {"religion": "pastafarian"}, "worship"),
    ("amenity", "place_of_worship", {}, "worship"),
])
def test_from_osm(cls, typ, extra, expected):
    assert categories.from_osm(cls, typ, extra) == expected


def test_geocoding_candidate_gets_category():
    assert parse_result(SAMPLE_RESULT).dest_category == "hospital"


DEST = {"name": "Stern-Apotheke", "address": "x", "lat": "48.5", "lon": "9.0", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "", "osm_type": "",
        "osm_id": ""}


def test_category_saved_and_shown(client):
    client.post("/locations", data={"name": "A", "address": "a", "lat": "48.5", "lon": "9.0"})
    client.post("/destinations", data=DEST | {"category": "pharmacy"})
    assert '<option value="pharmacy" selected>Apotheke</option>' in client.get("/destinations/1/edit").text
    assert 'categories/pharmacy.svg" alt="Apotheke"' in client.get("/destinations").text
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert 'pharmacy.svg" alt="Apotheke"' in page
    assert '"icon": "/static/categories/pharmacy.svg"' in page
    printout = client.get("/directions/print", params={"location_id": 1, "destination_id": 1}).text
    assert '<h1 class="with-icon"><img class="dest-icon"' in printout
    assert "Twemoji" not in printout   # own drawings, no attribution


def test_unknown_category_is_dropped(client):
    client.post("/destinations", data=DEST | {"category": "rocket"})
    assert '<option value="" >' in client.get("/destinations/1/edit").text or \
        "selected" not in client.get("/destinations/1/edit").text.split('name="category"')[1].split("</select>")[0]
