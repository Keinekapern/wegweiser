"""Language settings: which directions languages are offered."""

from app import db, languages

DEST = {"name": "Klinik", "address": "Weg 1", "lat": "48.53", "lon": "9.04", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "",
        "osm_type": "", "osm_id": "", "category": ""}


def _options(html: str, name: str) -> set[str]:
    import re
    block = html[html.index(f'name="{name}"'):]
    block = block[:block.index("</select>")]
    return set(re.findall(r'<option value="([a-z]+)"', block))


def test_all_languages_by_default(client):
    with db.get_conn() as conn:
        assert "ar" in languages.enabled(conn) and len(languages.enabled(conn)) > 20


def test_switch_languages_off(client, monkeypatch):
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    client.post("/destinations", data=DEST | {"name_tr": "Klinik TR", "name_ar": "عيادة"})
    page = client.get("/settings/languages").text
    assert 'value="de" checked disabled' in page
    r = client.post("/settings/languages", data={"langs": ["ar", "fa"]})
    assert "Gespeichert: 3 Sprachen" in r.text
    with db.get_conn() as conn:
        assert languages.enabled(conn) == ["de", "ar", "fa"]
    params = {"location_id": 1, "destination_id": 1, "profile": "foot-walking"}
    assert _options(client.get("/directions", params=params).text, "lang") == {"de", "ar", "fa"}
    # a link with a switched-off language falls back to German
    assert '<html lang="de"' in client.get("/directions/print", params=params | {"lang": "tr"}).text
    assert 'value="tr"' not in client.get("/export").text
    # destination form: only enabled languages; saving keeps the Turkish name
    form = client.get("/destinations/1/edit").text
    assert 'name="name_ar"' in form and 'name="name_tr"' not in form
    client.post("/destinations/1", data=DEST | {"name_ar": "عيادة 2"})
    with db.get_conn() as conn:
        assert db.get_destination_names(conn, 1) == {"ar": "عيادة 2", "tr": "Klinik TR"}


def test_language_settings_admins_only(client, anon_client, monkeypatch):
    r = anon_client.get("/settings/languages", follow_redirects=False)
    assert r.headers["location"].startswith("/admin/login")
    client.post("/locations", data={"name": "EA", "address": "x", "coords": "48.5, 9.0"})
    client.post("/destinations", data=DEST)
    params = {"location_id": 1, "destination_id": 1, "profile": "foot-walking"}
    assert "Sprachen auswählen" not in anon_client.get("/directions", params=params).text
    assert "Sprachen auswählen" in client.get("/directions", params=params).text
    assert "/settings/languages" in client.get("/admin").text
    monkeypatch.setenv("AUTH_MODE", "off")
    assert anon_client.get("/settings/languages").status_code == 200
