VALID = {
    "name": "Katharinenhospital",
    "address": "Kriegsbergstraße 60, 70174 Stuttgart",
    "lat": "48.784", "lon": "9.171",
    "phone": "+49 711 27801", "website": "klinikum-stuttgart.de",
    "opening_hours": "24/7", "google_maps_url": "", "note": "Haupteingang Kriegsbergstraße",
    "osm_type": "way", "osm_id": "4711",
}


def _create(client, **overrides):
    return client.post("/destinations", data=VALID | overrides, follow_redirects=False)


def test_empty_list(client):
    r = client.get("/destinations")
    assert r.status_code == 200
    assert "Noch keine Ziele" in r.text


def test_new_form_has_search_panel(client):
    r = client.get("/destinations/new")
    assert r.status_code == 200
    assert "data-geosearch" in r.text
    assert "geosearch.js" in r.text


def test_create_and_list(client):
    assert _create(client).status_code == 303
    page = client.get("/destinations").text
    assert "Katharinenhospital" in page
    assert "+49 711 27801" in page
    assert 'href="https://klinikum-stuttgart.de"' in page  # scheme added


def test_edit_shows_saved_values_and_osm_link(client):
    _create(client)
    page = client.get("/destinations/1/edit").text
    assert 'value="Haupteingang' not in page  # note is a textarea
    assert "Haupteingang Kriegsbergstraße</textarea>" in page
    assert "https://www.openstreetmap.org/way/4711" in page


def test_update(client):
    _create(client)
    r = client.post("/destinations/1", data=VALID | {"name": "KH Mitte", "osm_type": "", "osm_id": ""},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/destinations/1/edit").text
    assert 'value="KH Mitte"' in page
    assert "openstreetmap.org/way" not in page


def test_validation_errors_keep_input(client):
    r = _create(client, name="", lat="x", website="nicht gültig",
                google_maps_url="https://evil.example.com/maps")
    assert r.status_code == 422
    assert "Name darf nicht leer sein." in r.text
    assert "Breitengrad ist keine gültige Zahl." in r.text
    assert "Website ist keine gültige Web-Adresse." in r.text
    assert "Google-Maps-Link muss" in r.text
    assert 'value="+49 711 27801"' in r.text


def test_google_maps_url_accepted_hosts(client):
    for url in ("https://maps.app.goo.gl/abc", "https://www.google.com/maps/place/x",
                "https://www.google.de/maps?q=1"):
        assert _create(client, google_maps_url=url).status_code == 303, url
    assert _create(client, google_maps_url="https://google.com.evil.net/").status_code == 422


def test_malformed_osm_ref_is_dropped(client):
    assert _create(client, osm_type="node; DROP", osm_id="abc").status_code == 303
    assert "openstreetmap.org/" not in client.get("/destinations/1/edit").text.split("osm-ref")[1][:200]


def test_delete(client):
    _create(client)
    assert client.post("/destinations/1/delete", follow_redirects=False).status_code == 303
    assert "Noch keine Ziele" in client.get("/destinations").text


def test_missing_destination_404(client):
    assert client.get("/destinations/9/edit").status_code == 404
    assert client.post("/destinations/9", data=VALID).status_code == 404
    assert client.post("/destinations/9/delete").status_code == 404


def test_api_geocode(client, fake_nominatim):
    r = client.get("/api/geocode", params={"q": "Katharinenhospital"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["address"] == "Kriegsbergstraße 60, 70174 Stuttgart"
    assert "OpenStreetMap" in body["attribution"]
    assert body["cached"] is False
    assert client.get("/api/geocode", params={"q": "katharinenhospital"}).json()["cached"] is True
    assert len(fake_nominatim.requests) == 1


def test_api_geocode_rejects_short_query(client, fake_nominatim):
    assert client.get("/api/geocode", params={"q": "ab"}).status_code == 422
    assert fake_nominatim.requests == []


def test_api_geocode_upstream_error(client, fake_nominatim):
    fake_nominatim.status = 429
    r = client.get("/api/geocode", params={"q": "Katharinenhospital"})
    assert r.status_code == 502
    assert "abgelehnt" in r.json()["error"]


def test_locations_page_has_search_panel(client):
    assert "data-geosearch" in client.get("/locations").text
