"""AUTH_MODE=users: everyone logs in; roles admin / manager / staff per location."""

import pytest
from fastapi.testclient import TestClient

from app import auth, db

DEST = {"name": "Klinik", "address": "Weg 1", "lat": "48.53", "lon": "9.04", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "",
        "osm_type": "", "osm_id": "", "category": ""}
PASSWORD = "eigenes passwort"


@pytest.fixture
def users(client, monkeypatch):
    """Two locations (1 Nord, 2 Süd) and a function that logs in a new account."""
    monkeypatch.setenv("AUTH_MODE", "users")
    client.post("/locations", data={"name": "Unterkunft Nord", "address": "x", "coords": "48.5, 9.0"})
    client.post("/locations", data={"name": "Unterkunft Süd", "address": "y", "coords": "48.7, 9.0"})

    def login(name: str, role: str, locations: list[str]) -> TestClient:
        r = client.post("/admin/users", data={"username": name, "role": role,
                                              "location_ids": locations, "password": "start passwort"})
        assert "angelegt" in r.text, r.text
        from app.main import app
        browser = TestClient(app)
        browser.post("/admin/login", data={"username": name, "password": "start passwort"})
        browser.post("/admin/password", data={"current": "start passwort", "password": PASSWORD,
                                              "repeat": PASSWORD})
        return browser
    return login


def _dest(dest_id):
    with db.get_conn() as conn:
        return db.get_destination(conn, dest_id)


def _locs(dest_id):
    with db.get_conn() as conn:
        return db.locations_of_destination(conn, dest_id)


def test_everything_needs_login(users, anon_client):
    for url in ("/directions", "/destinations", "/locations", "/directions/print?location_id=1"):
        r = anon_client.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/admin/login?next=")
    r = anon_client.post("/destinations", data=DEST, follow_redirects=False)
    assert r.headers["location"].startswith("/admin/login")
    assert anon_client.get("/api/geocode", params={"q": "x"}).status_code == 401
    page = anon_client.get("/admin/login").text
    assert "<h1>Anmeldung</h1>" in page and 'class="login-link"' not in page
    assert anon_client.get("/static/style.css").status_code == 200
    assert anon_client.get("/healthz").status_code == 200
    assert _dest(1) is None


def test_pdf_renderer_gets_in_with_its_token(users, client, anon_client):
    client.post("/destinations", data=DEST)
    url = "/directions/print?location_id=1&destination_id=1&profile=foot-walking"
    anon_client.cookies.set(auth.RENDER_COOKIE, "geraten")
    assert anon_client.get(url, follow_redirects=False).status_code == 303
    anon_client.cookies.set(auth.RENDER_COOKIE, auth.render_token())
    assert anon_client.get(url).status_code == 200
    r = anon_client.post("/destinations", data=DEST, follow_redirects=False)   # GET only
    assert r.headers["location"].startswith("/admin/login")


def test_new_account_needs_locations(users, client):
    r = client.post("/admin/users", data={"username": "x", "role": "staff"})
    assert r.status_code == 422 and "mindestens einen Standort" in r.text
    page = client.get("/admin").text
    assert "Konten" in page and "Rolle" in page and "Standortverantwortlich" in page


def test_staff_proposals_go_to_their_location_and_its_manager(users, client):
    staff = users("ina", "staff", ["2"])
    nord = users("nora", "manager", ["1"])
    sued = users("sven", "manager", ["2"])
    assert "Standorte, für die das Ziel angeboten wird" not in staff.get("/destinations/new").text
    staff.post("/destinations", data=DEST | {"location_ids": ["1"]})   # not hers: ignored
    assert _dest(1).status == "pending" and _locs(1) == [2]
    # the manager of Süd sees and approves it, the one of Nord does not
    assert "Klinik" not in nord.get("/admin").text.split("Neue Ziele zur Bestätigung")[1]
    assert nord.post("/admin/destinations/1/approve").status_code == 404
    page = sued.get("/admin").text
    assert "Klinik" in page and '<span class="count"' in page
    sued.post("/admin/destinations/1/approve")
    with db.get_conn() as conn:
        assert _dest(1).status == "approved"
        assert conn.execute("SELECT approved_by FROM destinations").fetchone()[0] == "sven"
    # staff may not change it any more, nor anything else of the administration
    assert staff.get("/destinations/1/edit", follow_redirects=False).status_code == 404
    for url in ("/locations/1/edit", "/settings/languages", "/export", "/admin/users/1"):
        assert staff.get(url, follow_redirects=False).status_code == 404, url
    assert "Konten" not in staff.get("/admin").text


def test_manager_edits_only_destinations_of_own_locations(users, client):
    client.post("/destinations", data=DEST | {"name": "Für alle"})                     # 1
    client.post("/destinations", data=DEST | {"name": "Nord", "location_ids": ["1"]})  # 2
    client.post("/destinations", data=DEST | {"name": "Beide", "location_ids": ["1", "2"]})  # 3
    nora = users("nora", "manager", ["1"])
    listing = nora.get("/destinations").text
    assert "/destinations/2/edit" in listing
    assert "/destinations/1/edit" not in listing and "/destinations/3/edit" not in listing
    for dest_id in (1, 3):
        assert nora.post(f"/destinations/{dest_id}/delete", follow_redirects=False).status_code == 404
    # assigning: only her own locations; none ticked = her own, never "all locations"
    form = nora.get("/destinations/2/edit").text
    assert "Unterkunft Nord" in form and 'value="2"' not in form.split("location-checks")[1].split("</fieldset>")[0]
    nora.post("/destinations/2", data=DEST | {"name": "Nord", "location_ids": ["1", "2"]})
    assert _locs(2) == [1]
    nora.post("/destinations/2", data=DEST | {"name": "Nord neu"})
    assert _locs(2) == [1] and _dest(2).name == "Nord neu"
    # her own new destinations are approved at once, at her locations
    nora.post("/destinations", data=DEST | {"name": "Praxis"})
    assert _dest(4).status == "approved" and _locs(4) == [1]
    nora.post("/destinations/2/delete")
    assert _dest(2) is None


def test_own_location_is_preselected(users, client):
    client.post("/destinations", data=DEST)
    sven = users("sven", "manager", ["2"])
    page = sven.get("/directions").text
    assert '<option value="2" selected>Unterkunft Süd' in page


def test_admin_cannot_lock_themselves_out(users, client):
    r = client.post("/admin/users/1", data={"role": "staff", "location_ids": ["1"]})
    assert r.status_code == 422 and "eigene Rolle" in r.text
    users("nora", "manager", ["1"])
    client.post("/admin/users/2", data={"role": "admin"})
    with db.get_conn() as conn:
        nora = db.get_account(conn, 2)
        assert nora.role == "admin" and nora.location_ids == ()
    client.post("/admin/users/2", data={"role": "staff", "location_ids": ["2"]})
    with db.get_conn() as conn:
        assert db.get_account(conn, 2).location_ids == (2,)
    page = client.get("/admin/users/2").text
    assert "Konto „nora“" in page and 'value="staff" checked' in page
    assert 'name="location_ids" value="2" checked' in page


def test_deleting_a_location_removes_it_from_accounts(users, client):
    users("nora", "manager", ["1", "2"])
    client.post("/locations/1/delete")
    with db.get_conn() as conn:
        assert db.get_account(conn, 2).location_ids == (2,)


def test_roles_also_apply_in_admin_mode(users, client, monkeypatch):
    """Accounts created in AUTH_MODE=users keep their limits if the mode is switched back."""
    staff = users("ina", "staff", ["2"])
    monkeypatch.setenv("AUTH_MODE", "admin")
    assert staff.get("/locations/1/edit", follow_redirects=False).status_code == 404
    assert staff.get("/directions").status_code == 200
