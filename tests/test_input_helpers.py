import pytest

from app.validation import normalize_phone, parse_coordinates

DEST = {"name": "Praxis", "address": "x", "phone": "", "website": "", "opening_hours": "",
        "google_maps_url": "", "note": "", "osm_type": "", "osm_id": ""}


@pytest.mark.parametrize("raw,expected", [
    ("07071/29-0", "+49 7071 29-0"),
    ("0049 7071 290", "+49 7071 290"),
    ("+49 (0)7071 290", "+49 7071 290"),
    ("(07071) 29 0", "+49 7071 29 0"),
    ("+497071290", "+49 7071290"),
    ("0043 1 234567", "+43 1 234567"),
    ("+49 7071 29-0", "+49 7071 29-0"),
    ("", ""),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("48.690351, 9.032999", (48.690351, 9.032999)),
    ("48.690351,9.032999", (48.690351, 9.032999)),
    ("48.690351 9.032999", (48.690351, 9.032999)),
    ("(48.690351, 9.032999)", (48.690351, 9.032999)),
    ("48,69 9,03", (48.69, 9.03)),
    ("48.6; 9.0", (48.6, 9.0)),
])
def test_parse_coordinates(raw, expected):
    errors = []
    assert parse_coordinates(raw, errors) == expected
    assert errors == []


@pytest.mark.parametrize("raw", ["abc", "48.6", "48.6, 9.0, 1", "95.0, 9.0"])
def test_parse_coordinates_invalid(raw):
    errors = []
    assert None in parse_coordinates(raw, errors)
    assert errors


def test_destination_form_combined_coords_and_phone(client):
    r = client.post("/destinations", data=DEST | {"coords": "48.690351, 9.032999",
                                                   "phone": "07071/29-0"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/destinations/1/edit").text
    assert 'name="coords" required inputmode="decimal" value="48.690351, 9.032999"' in page
    assert 'value="+49 7071 29-0"' in page
    assert "In Google Maps suchen" in page and "destination-form.js" in page


def test_destination_form_errors(client):
    r = client.post("/destinations", data=DEST | {"coords": "irgendwo", "phone": "29"})
    assert r.status_code == 422
    assert "Koordinaten nicht erkannt" in r.text
    assert "Telefonnummer „29“ ist ungültig" in r.text
    assert 'value="irgendwo"' in r.text   # input kept


def test_location_form_combined_coords(client):
    r = client.post("/locations", data={"name": "EA", "address": "a",
                                        "coords": "48.52, 9.05"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/locations").text
    assert "48.520000, 9.050000" in page
    assert "categories/location.svg" in page     # house symbol
    assert 'value="48.52, 9.05"' in client.get("/locations/1/edit").text


def test_existing_phones_are_normalized_once(tmp_path):
    from app import db
    c = db.connect(tmp_path / "p.sqlite")
    db.migrate(c)
    c.execute("INSERT INTO destinations (name, address, lat, lon, phone) VALUES ('A','x',1,1,'07071/29-0')")
    c.commit()
    db.normalize_existing_phones(c)
    assert c.execute("SELECT phone FROM destinations").fetchone()[0] == "+49 7071 29-0"
    c.execute("UPDATE destinations SET phone = '0711 1'")
    c.commit()
    db.normalize_existing_phones(c)   # second run does nothing
    assert c.execute("SELECT phone FROM destinations").fetchone()[0] == "0711 1"
