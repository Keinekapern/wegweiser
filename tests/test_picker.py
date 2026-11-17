import re

from app import categories

BASE = {"address": "x", "coords": "48.5, 9.0", "phone": "", "website": "",
        "opening_hours": "", "google_maps_url": "", "note": "", "osm_type": "", "osm_id": ""}


def _setup(client):
    client.post("/locations", data={"name": "EA", "address": "a", "coords": "48.5, 9.0"})
    client.post("/destinations", data=BASE | {"name": "Zahnarzt Müller", "category": "dentist"})
    client.post("/destinations", data=BASE | {"name": "Bären Apotheke", "category": "pharmacy"})
    client.post("/destinations", data=BASE | {"name": "Uniklinik", "category": "hospital"})
    client.post("/destinations", data=BASE | {"name": "Irgendwas"})
    client.post("/destinations", data=BASE | {"name": "Adler Apotheke", "category": "pharmacy"})


def test_new_categories():
    assert categories.get("optician").label == "Optiker"
    assert categories.get("physio").label == "Physiotherapie"
    assert categories.from_osm("shop", "optician") == "optician"
    assert categories.from_osm("healthcare", "physiotherapist") == "physio"


def test_destinations_grouped_by_category(client):
    _setup(client)
    page = client.get("/directions").text
    groups = re.findall(r'<optgroup label="([^"]+)">', page)
    assert groups == ["Krankenhaus", "Zahnarzt", "Apotheke", "Ohne Kategorie"]
    names = re.findall(r'<option value="\d+" data-locations[^>]*>([^<]+)</option>', page)
    assert names == ["Uniklinik", "Zahnarzt Müller", "Adler Apotheke", "Bären Apotheke", "Irgendwas"]
    assert 'data-picker' in page and "destination-picker.js" in page
    assert 'data-icon="http://testserver/static/categories/pharmacy.svg"' in page
    assert 'data-create="„{q}“ als neues Ziel anlegen"' in page


def test_new_destination_prefilled_from_picker(client):
    client.post("/locations", data={"name": "EA", "address": "a", "coords": "48.5, 9.0"})
    page = client.get("/destinations/new", params={"name": "Augenarzt Dr. X", "location_id": 1}).text
    assert 'name="name" required value="Augenarzt Dr. X"' in page
    assert "data-autosearch" in page
    assert 'name="q" minlength="3" maxlength="200" value="Augenarzt Dr. X"' in page
    assert 'name="location_ids" value="1" checked' in page
    assert "data-autosearch" not in client.get("/destinations/new").text


def test_steps_unchecked_by_default_in_print_view(client, fake_ors):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 3,
                                                   "profile": "foot-walking"}).text
    assert '<input type="checkbox" id="toggle-steps">' in page
    assert "<body>" in page   # no "with-steps" class
