import tempfile
from pathlib import Path

from app import db

BASE = {"address": "x", "lat": "48.5", "lon": "9.0", "phone": "", "website": "",
        "opening_hours": "", "google_maps_url": "", "note": "", "osm_type": "", "osm_id": ""}


def _loc(client, name):
    client.post("/locations", data={"name": name, "address": "a", "lat": "48.5", "lon": "9.0"})


def _dest(client, name, location_ids=()):
    return client.post("/destinations", data=BASE | {"name": name,
                                                      "location_ids": [str(i) for i in location_ids]},
                       follow_redirects=False)


def _setup(client):
    _loc(client, "Tübingen")      # 1
    _loc(client, "Reutlingen")    # 2
    _dest(client, "Uniklinik", [1])
    _dest(client, "Kreiskliniken", [2])
    _dest(client, "Landratsamt", [1, 2])
    _dest(client, "Bürgeramt")    # unassigned -> everywhere


def test_migration_assigns_existing_destinations_to_single_location():
    c = db.connect(Path(tempfile.mkdtemp()) / "m.sqlite")
    c.executescript("".join(db.MIGRATIONS[:5]))
    c.execute("PRAGMA user_version = 5")
    c.execute("INSERT INTO locations (name, address, lat, lon) VALUES ('A', 'x', 1, 1)")
    c.execute("INSERT INTO destinations (name, address, lat, lon) VALUES ('Z', 'y', 1, 1)")
    c.commit()
    db.migrate(c)
    assert db.destination_location_ids(c) == {1: [1]}


def test_migration_leaves_destinations_unassigned_with_several_locations():
    c = db.connect(Path(tempfile.mkdtemp()) / "m.sqlite")
    c.executescript("".join(db.MIGRATIONS[:5]))
    c.execute("PRAGMA user_version = 5")
    c.execute("INSERT INTO locations (name, address, lat, lon) VALUES ('A', 'x', 1, 1), ('B', 'x', 1, 1)")
    c.execute("INSERT INTO destinations (name, address, lat, lon) VALUES ('Z', 'y', 1, 1)")
    c.commit()
    db.migrate(c)
    assert db.destination_location_ids(c) == {}


def test_list_destinations_by_location(client):
    _setup(client)
    with db.get_conn() as conn:
        names = lambda lid: [d.name for d in db.list_destinations(conn, lid)]
        assert names(None) == ["Bürgeramt", "Kreiskliniken", "Landratsamt", "Uniklinik"]
        assert names(1) == ["Bürgeramt", "Landratsamt", "Uniklinik"]
        assert names(2) == ["Bürgeramt", "Kreiskliniken", "Landratsamt"]


def test_form_saves_and_shows_assignments(client):
    _setup(client)
    page = client.get("/destinations/3/edit").text
    assert 'name="location_ids" value="1" checked' in page
    assert 'name="location_ids" value="2" checked' in page
    client.post("/destinations/3", data=BASE | {"name": "Landratsamt", "location_ids": ["2"]})
    page = client.get("/destinations/3/edit").text
    assert 'name="location_ids" value="1" >' in page
    assert 'name="location_ids" value="2" checked' in page
    # unknown ids are ignored
    client.post("/destinations/3", data=BASE | {"name": "Landratsamt", "location_ids": ["99", "x"]})
    with db.get_conn() as conn:
        assert db.destination_location_ids(conn).get(3) is None


def test_new_form_preselects_location(client):
    _loc(client, "Tübingen")
    assert 'name="location_ids" value="1" checked' in client.get("/destinations/new").text
    _loc(client, "Reutlingen")
    page = client.get("/destinations/new").text
    assert "checked" not in page.split("location-checks")[1].split("</fieldset>")[0]
    page = client.get("/destinations/new", params={"location_id": 2}).text
    assert 'name="location_ids" value="2" checked' in page


def test_list_filter_and_column(client):
    _setup(client)
    page = client.get("/destinations", params={"location_id": 2}).text
    assert "Kreiskliniken" in page and "Uniklinik" not in page
    assert "Tübingen, Reutlingen" in page    # Landratsamt
    assert ">alle</span>" in page             # Bürgeramt
    assert 'href="/destinations/new?location_id=2"' in page
    assert "Uniklinik" in client.get("/destinations").text


def test_deleting_location_removes_assignment(client):
    _setup(client)
    client.post("/locations/2/delete")
    with db.get_conn() as conn:
        assert db.destination_location_ids(conn) == {1: [1], 3: [1]}


def test_directions_dropdown_is_filtered(client):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1}).text
    import re
    opt = lambda value: re.search(rf'<option value="{value}" data-locations="([^"]*)"[^>]*?( hidden disabled)?>([^<]*)</option>', page)
    assert opt(2).groups() == ("2", " hidden disabled", "Kreiskliniken")
    assert opt(1).groups() == ("1", None, "Uniklinik")
    assert opt(4).groups() == ("", None, "Bürgeramt")
    assert opt(3).groups() == ("1,2", None, "Landratsamt")


def test_route_button_preselects_assigned_location(client):
    _setup(client)
    page = client.get("/directions", params={"destination_id": 2}).text
    assert '<option value="2" selected>Reutlingen</option>' in page
    page = client.get("/directions", params={"destination_id": 3}).text  # two locations
    assert '<option value="1" selected>Tübingen</option>' not in page
    assert '<option value="2" selected>Reutlingen</option>' not in page
