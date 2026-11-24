"""Admin login, who may change what, approval of destinations created without login."""

import pytest
from fastapi.testclient import TestClient

from app import admin_cli, auth, db
from tests.conftest import ADMIN_PASSWORD, ADMIN_USER

DEST = {"name": "Klinik", "address": "Weg 1", "lat": "48.53", "lon": "9.04", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "",
        "osm_type": "", "osm_id": "", "category": ""}


def _status(dest_id):
    with db.get_conn() as conn:
        return db.get_destination(conn, dest_id).status


def _ids():
    with db.get_conn() as conn:
        return [d.id for d in db.list_destinations(conn)]


def test_password_hash_roundtrip():
    stored = auth.hash_password("geheimes passwort")
    assert stored.startswith("scrypt$")
    assert auth.verify_password("geheimes passwort", stored)
    assert not auth.verify_password("falsch", stored)
    assert not auth.verify_password("x", "md5$abc")
    assert not auth.verify_password("x", "kaputt")


def test_login_logout(client, anon_client):
    page = anon_client.get("/admin", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/admin/login?next=%2Fadmin"
    r = anon_client.post("/admin/login", data={"username": ADMIN_USER, "password": "falsch"})
    assert r.status_code == 401 and "Benutzername oder Passwort ist falsch." in r.text
    r = anon_client.post("/admin/login", data={"username": ADMIN_USER.upper(),
                                               "password": ADMIN_PASSWORD, "next": "/locations"},
                         follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/locations"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Angemeldet als admin" in anon_client.get("/admin").text
    anon_client.post("/admin/logout")
    assert anon_client.get("/admin", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("next_url", ["https://evil.example", "//evil.example", "/\\evil"])
def test_login_no_open_redirect(anon_client, client, next_url):
    r = anon_client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD,
                                               "next": next_url}, follow_redirects=False)
    assert r.headers["location"] == "/admin"


def test_login_locked_after_failures(client, anon_client):
    for _ in range(5):
        anon_client.post("/admin/login", data={"username": "admin", "password": "falsch"})
    r = anon_client.post("/admin/login", data={"username": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 401 and "Zu viele Fehlversuche" in r.text
    auth.clear_failures("admin")


def test_locations_only_for_admins(client, anon_client):
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    page = anon_client.get("/locations").text
    assert "EA" in page and 'id="location-form"' not in page and "/locations/1/edit" not in page
    for url in ("/locations", "/locations/1", "/locations/1/delete"):
        r = anon_client.post(url, data={"name": "X", "address": "y", "coords": "1, 2"},
                             follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/admin/login")
    assert anon_client.get("/locations/1/edit", follow_redirects=False).headers["location"] \
        == "/admin/login?next=%2Flocations%2F1%2Fedit"
    with db.get_conn() as conn:
        assert db.get_location(conn, 1).name == "EA"


def test_admin_creates_approved_destination(client):
    client.post("/destinations", data=DEST)
    assert _status(1) == "approved"


def test_anonymous_destination_is_pending_and_usable(client, anon_client):
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    client.post("/locations", data={"name": "Unterkunft Süd", "address": "y", "coords": "48.7, 9.0"})
    r = anon_client.post("/destinations", data=DEST | {"location_ids": ["2", "1"]},
                         follow_redirects=False)
    assert r.headers["location"] == "/destinations?created=pending"
    assert auth.CREATOR_COOKIE in r.headers["set-cookie"]
    assert _status(1) == "pending"
    with db.get_conn() as conn:
        assert db.destination_location_ids(conn)[1] == [2]   # only the first, no free assignment
    listing = anon_client.get("/destinations?created=pending").text
    assert "sofort nutzbar" in listing and "unbestätigt" in listing
    assert "/destinations/1/edit" in listing                 # own pending destination
    picker = anon_client.get("/directions", params={"location_id": 2}).text
    assert "Klinik (unbestätigt)" in picker and 'data-icon="http://testserver/static/categories/pending.svg"' in picker
    assert 'src="http://testserver/static/categories/pending.svg"' in listing
    # usable for directions right away
    assert anon_client.get("/directions/print", params={"location_id": 2, "destination_id": 1,
                                                        "profile": "foot-walking"}).status_code == 200


def test_creator_may_correct_own_pending_destination_only(client, anon_client):
    anon_client.post("/destinations", data=DEST)
    page = anon_client.get("/destinations/1/edit")
    assert page.status_code == 200 and 'name="location_ids"' not in page.text
    anon_client.post("/destinations/1", data=DEST | {"name": "Kinderklinik"})
    with db.get_conn() as conn:
        assert db.get_destination(conn, 1).name == "Kinderklinik"
    # another browser without login may not
    from app.main import app
    other = TestClient(app)
    assert "/destinations/1/edit" not in other.get("/destinations").text
    r = other.post("/destinations/1/delete", follow_redirects=False)
    assert r.headers["location"].startswith("/admin/login")
    # after approval, the creator may not either
    client.post("/admin/destinations/1/approve")
    with db.get_conn() as conn:
        dest = db.get_destination(conn, 1)
        assert dest.status == "approved" and db.destination_creator_token(conn, 1) is None
        assert conn.execute("SELECT approved_by FROM destinations").fetchone()[0] == ADMIN_USER
    assert anon_client.get("/destinations/1/edit", follow_redirects=False).status_code == 303
    assert anon_client.post("/destinations/1/delete", follow_redirects=False).status_code == 303
    assert _ids() == [1]


def test_creator_may_withdraw_own_pending_destination(client, anon_client):
    anon_client.post("/destinations", data=DEST)
    anon_client.post("/destinations/1/delete")
    assert _ids() == []


def test_admin_dashboard_approve_and_reject(client, anon_client):
    anon_client.post("/destinations", data=DEST)
    anon_client.post("/destinations", data=DEST | {"name": "Praxis"})
    page = client.get("/admin").text
    assert "Neue Ziele zur Bestätigung" in page and "Klinik" in page and "Praxis" in page
    assert '<span class="count"' in client.get("/directions").text      # badge in the nav
    r = client.post("/admin/destinations/1/approve", follow_redirects=False)
    assert r.headers["location"] == "/admin"
    client.post("/destinations/2/delete", headers={"referer": "http://testserver/admin"})
    assert _ids() == [1] and _status(1) == "approved"
    assert "Keine Ziele warten auf Bestätigung." in client.get("/admin").text
    assert client.post("/admin/destinations/1/approve").status_code == 404   # not pending


def test_anonymous_cannot_save_transit_defaults(client, anon_client):
    r = anon_client.post("/directions/transit-defaults", data={"max_transfers": "1"},
                         follow_redirects=False)
    assert r.headers["location"].startswith("/admin/login")
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    client.post("/destinations", data=DEST)
    params = {"location_id": 1, "destination_id": 1, "profile": "transit"}
    assert "Als Standard speichern" not in anon_client.get("/directions", params=params).text
    assert "Als Standard speichern" in client.get("/directions", params=params).text


def test_manage_admins(client, anon_client):
    r = client.post("/admin/users", data={"username": "zwei", "password": "kurz"})
    assert r.status_code == 422 and "mindestens 10 Zeichen" in r.text
    r = client.post("/admin/users", data={"username": "ADMIN", "password": "x" * 12})
    assert "Diesen Benutzernamen gibt es schon." in r.text
    r = client.post("/admin/users", data={"username": "zwei", "password": "x" * 12,
                                          "role": "staff"})     # no roles in AUTH_MODE=admin
    assert "Konto „zwei“ angelegt." in r.text and "x" * 12 in r.text
    with db.get_conn() as conn:
        zwei = db.get_account(conn, 2)
        assert zwei.role == "admin" and zwei.must_change_password
    # an empty start password is generated and shown once
    r = client.post("/admin/users", data={"username": "drei"})
    generated = r.text.split('<code class="secret">')[1].split("<")[0]
    assert len(generated) == 12
    assert anon_client.post("/admin/login", data={"username": "drei", "password": generated},
                            follow_redirects=False).headers["location"] == "/admin"
    assert "Das eigene Konto kann nicht gelöscht werden." in client.post("/admin/users/1/delete").text
    client.post("/admin/users/2/delete")
    client.post("/admin/users/3/delete")
    with db.get_conn() as conn:
        assert [a.username for a in db.list_accounts(conn)] == [ADMIN_USER]


def test_start_password_must_be_changed_first(client, anon_client):
    client.post("/admin/users", data={"username": "neu", "password": "start passwort"})
    r = anon_client.post("/admin/login", data={"username": "neu", "password": "start passwort",
                                               "next": "/locations"}, follow_redirects=False)
    assert r.headers["location"] == "/admin"
    for url in ("/directions", "/locations", "/settings/languages"):
        assert anon_client.get(url, follow_redirects=False).headers["location"] == "/admin"
    page = anon_client.get("/admin").text
    assert "Bitte zuerst ein eigenes Passwort festlegen" in page and "Konten" not in page
    r = anon_client.post("/admin/password", data={"current": "start passwort",
                                                  "password": "start passwort", "repeat": "start passwort"})
    assert "nicht das bisherige" in r.text
    anon_client.post("/admin/password", data={"current": "start passwort",
                                              "password": "eigenes passwort", "repeat": "eigenes passwort"})
    assert anon_client.get("/directions").status_code == 200


def test_reset_password_of_another_account(client, anon_client):
    client.post("/admin/users", data={"username": "zwei", "password": "x" * 12})
    anon_client.post("/admin/login", data={"username": "zwei", "password": "x" * 12})
    assert anon_client.get("/admin", follow_redirects=False).status_code == 200
    page = client.post("/admin/users/2/password").text
    new = page.split('<code class="secret">')[1].split("<")[0]
    assert anon_client.get("/admin", follow_redirects=False).status_code == 303   # session ended
    with db.get_conn() as conn:
        assert auth.authenticate(conn, "zwei", new) is not None
    assert client.post("/admin/users/1/password").status_code == 404           # not the own


def test_password_change_ends_other_sessions(client, anon_client):
    anon_client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert anon_client.get("/admin", follow_redirects=False).status_code == 200
    r = client.post("/admin/password", data={"current": "falsch", "password": "y" * 12,
                                             "repeat": "y" * 12})
    assert "Das bisherige Passwort ist falsch." in r.text
    r = client.post("/admin/password", data={"current": ADMIN_PASSWORD, "password": "y" * 12,
                                             "repeat": "y" * 12})
    assert "Passwort geändert." in r.text
    assert client.get("/admin", follow_redirects=False).status_code == 200     # this session stays
    assert anon_client.get("/admin", follow_redirects=False).status_code == 303


def test_cli_create_and_delete(client, monkeypatch, capsys):
    answers = iter(["kurz", "lang genug 123", "lang genug 123"])
    monkeypatch.setattr(admin_cli.getpass, "getpass", lambda prompt="": next(answers))
    assert admin_cli.main(["create", "moritz"]) == 0
    assert admin_cli.main(["create", "moritz"]) == 1
    with db.get_conn() as conn:
        assert auth.authenticate(conn, "moritz", "lang genug 123") is not None
    assert admin_cli.main(["delete", "moritz"]) == 0
    assert admin_cli.main(["list"]) == 0
    assert capsys.readouterr().out.strip().endswith(ADMIN_USER)
    assert admin_cli.main([]) == 2


def test_login_page_explains_first_admin(anon_client, tmp_path, monkeypatch):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM admins")
        conn.commit()
    assert "python -m app.admin_cli create" in anon_client.get("/admin/login").text


# --- AUTH_MODE=off: no login, everyone may change everything ---

def test_auth_mode_off_everyone_may_change_everything(client, anon_client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "off")
    page = anon_client.get("/directions").text
    assert "Betrieb ohne Anmeldung" in page and "/admin/login" not in page
    anon_client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    anon_client.post("/destinations", data=DEST | {"location_ids": ["1"]})
    assert _status(1) == "approved"                        # no approval step
    with db.get_conn() as conn:
        assert db.get_location(conn, 1).name == "EA"
        assert db.destination_location_ids(conn)[1] == [1]
    assert 'name="location_ids"' in anon_client.get("/destinations/1/edit").text
    anon_client.post("/destinations/1", data=DEST | {"name": "Kinderklinik"})
    r = anon_client.post("/directions/transit-defaults", data={"max_transfers": "1"},
                         follow_redirects=False)
    assert not r.headers.get("location", "").startswith("/admin/login")
    anon_client.post("/destinations/1/delete")
    anon_client.post("/locations/1/delete")
    assert _ids() == []
    # nothing to administer; an old admin session cookie counts for nothing
    assert anon_client.get("/admin").status_code == 404
    assert anon_client.get("/admin/login").status_code == 404
    assert client.get("/admin").status_code == 404


def test_auth_mode_off_refused_behind_tunnel(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("AUTH_MODE", "off")
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "secret")
    from app.main import app
    with pytest.raises(RuntimeError, match="AUTH_MODE=off"):
        with TestClient(app):
            pass


def test_invalid_auth_mode(monkeypatch):
    from app import config
    monkeypatch.setenv("AUTH_MODE", "everyone")
    with pytest.raises(ValueError, match="AUTH_MODE"):
        config.auth_mode()


def test_unknown_action_is_a_bug(client):
    from starlette.requests import Request
    with pytest.raises(ValueError, match="unknown action"):
        auth.can(Request({"type": "http", "headers": [], "query_string": b""}), "everything")


def test_auth_mode_off_hides_pending_marks(client, anon_client, monkeypatch):
    anon_client.post("/destinations", data=DEST)          # pending, created in admin mode
    monkeypatch.setenv("AUTH_MODE", "off")
    listing = anon_client.get("/destinations").text
    assert "pending.svg" not in listing and "unbestätigt" not in listing
    assert _status(1) == "pending"                         # data unchanged, shows again in admin mode


def test_print_credit_can_be_switched_off(client, anon_client):
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    client.post("/destinations", data=DEST)
    url = "/directions/print?location_id=1&destination_id=1&profile=foot-walking"
    assert 'class="credit">Wegweiser (github.com/Keinekapern/wegweiser)' in client.get(url).text
    assert anon_client.get("/settings/print", follow_redirects=False).headers["location"].startswith("/admin/login")
    assert "/settings/print" in client.get("/admin").text
    page = client.post("/settings/print", data={}).text
    assert "Gespeichert." in page and "checked" not in page.split('name="credit"')[1].split(">")[0]
    assert 'class="credit"' not in client.get(url).text
    client.post("/settings/print", data={"credit": "1"})
    assert 'class="credit"' in client.get(url + "&lang=ar").text
