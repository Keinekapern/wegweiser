"""Entering several destinations: "Anlegen und nächstes Ziel" and the bulk page."""

import json

from app import auth, db

DEST = {"name": "Klinik", "address": "Weg 1", "coords": "48.53, 9.04", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "",
        "osm_type": "", "osm_id": "", "category": ""}


def _item(name, osm_id, **extra):
    return json.dumps({"name": name, "address": "Weg 1, 12345 Musterstadt", "display_name": "x",
                       "lat": 48.5, "lon": 9.05, "phone": "07071 123", "website": "",
                       "opening_hours": "Mo-Fr 08:00-12:00", "osm_type": "node", "osm_id": osm_id,
                       "category": "amenity", "type": "doctors", "dest_category": "doctor",
                       **extra})


def _locations(client):
    client.post("/locations", data={"name": "Unterkunft Nord", "address": "x", "coords": "48.5, 9.0"})
    client.post("/locations", data={"name": "Unterkunft Süd", "address": "y", "coords": "48.7, 9.0"})


def _all():
    with db.get_conn() as conn:
        return db.list_destinations(conn), db.destination_location_ids(conn)


def test_create_and_next_keeps_locations(client):
    _locations(client)
    r = client.post("/destinations", data=DEST | {"location_ids": ["2"], "next": "1"},
                    follow_redirects=False)
    assert r.headers["location"] == "/destinations/new?saved=1&location_id=2"
    page = client.get(r.headers["location"]).text
    assert "„Klinik“ angelegt" in page
    assert 'name="location_ids" value="2" checked' in page
    assert 'name="location_ids" value="1" checked' not in page
    assert 'value="Klinik"' not in page            # empty form
    # without ticks (all locations) nothing is carried over
    r = client.post("/destinations", data=DEST | {"next": "1"}, follow_redirects=False)
    assert r.headers["location"] == "/destinations/new?saved=2"


def test_create_and_next_without_login(client, anon_client):
    _locations(client)
    r = anon_client.post("/destinations", data=DEST | {"location_ids": ["1"], "next": "1"},
                         follow_redirects=False)
    assert r.headers["location"] == "/destinations/new?saved=1&location_id=1"
    assert auth.CREATOR_COOKIE in r.cookies
    page = anon_client.get(r.headers["location"]).text
    assert '<input type="hidden" name="location_ids" value="1">' in page
    dests, locs = _all()
    assert dests[0].pending and locs[1] == [1]


def test_bulk_page_lists_known_osm_objects(client):
    client.post("/destinations", data=DEST | {"osm_type": "node", "osm_id": "77"})
    page = client.get("/destinations/bulk").text
    data = json.loads(page.split('<script id="bulk-data" type="application/json">')[1].split("</script>")[0])
    assert data == {"max": 30, "existing": {"node/77": "Klinik"}}
    assert "Mehrere Ziele auf einmal" in client.get("/destinations").text


def test_bulk_create(client):
    _locations(client)
    r = client.post("/destinations/bulk", data={
        "location_ids": ["1"],
        "item": [_item("Praxis A", 1, names={"en": "Practice A", "xx": "?", "de": "nein"}),
                 _item("Praxis B", 2, category="pharmacy"),
                 _item("Ohne Adresse", 3, address=""),
                 "kein json", "[1]"]})
    assert r.status_code == 200
    assert "2 Ziele angelegt." in r.text and "Ohne Adresse" in r.text
    assert "/destinations/new?name=Ohne%20Adresse" in r.text
    dests, locs = _all()
    by_name = {d.name: d for d in dests}
    assert set(by_name) == {"Praxis A", "Praxis B"}
    a = by_name["Praxis A"]
    assert not a.pending and a.phone == "+49 7071 123" and a.osm_id == 1
    assert a.category == ""        # OSM "category" is not ours; the page sends our key
    assert by_name["Praxis B"].category == "pharmacy"
    assert locs[a.id] == [1]
    with db.get_conn() as conn:
        assert db.get_destination_names(conn, a.id) == {"en": "Practice A"}


def test_bulk_create_without_login_makes_proposals(client, anon_client):
    _locations(client)
    r = anon_client.post("/destinations/bulk", data={
        "location_ids": ["2", "1"], "item": [_item("Praxis A", 1), _item("Praxis B", 2)]})
    assert "2 Ziele angelegt." in r.text and "Neue Ziele sind sofort nutzbar" in r.text
    assert auth.CREATOR_COOKIE in r.cookies
    dests, locs = _all()
    assert all(d.pending for d in dests) and all(locs[d.id] == [2] for d in dests)
    for d in dests:   # both editable from the same browser (one creator cookie)
        assert anon_client.get(f"/destinations/{d.id}/edit").status_code == 200


def test_bulk_is_limited(client):
    from app.routes.destinations import MAX_BULK
    client.post("/destinations/bulk", data={"item": [_item(f"P{i}", i) for i in range(MAX_BULK + 5)]})
    assert len(_all()[0]) == MAX_BULK
