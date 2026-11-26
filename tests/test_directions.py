import json
from app.deps import stop_name

LOC = {"name": "Büro Mitte", "address": "Hauptstr. 1, 70173 Stuttgart", "lat": "48.77", "lon": "9.18"}
DEST = {"name": "Katharinenhospital", "address": "Kriegsbergstraße 60, 70174 Stuttgart",
        "lat": "48.784", "lon": "9.171", "phone": "", "website": "", "opening_hours": "",
        "google_maps_url": "", "note": "", "osm_type": "", "osm_id": ""}


def _setup(client):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST)


def test_hint_when_nothing_configured(client):
    page = client.get("/directions").text
    assert 'href="/locations"' in page and "anlegen" in page


def test_selection_without_route(client, fake_ors):
    _setup(client)
    page = client.get("/directions").text
    assert "Route berechnen" in page
    assert 'id="map"' not in page
    assert fake_ors.requests == []


def test_single_location_is_preselected(client):
    _setup(client)
    assert '<option value="1" selected>Büro Mitte</option>' in client.get("/directions").text


def test_route_is_rendered(client, fake_ors):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "foot-walking"}).text
    # no category: the "not categorised" symbol before the name
    assert ('<h2 class="with-icon"><img class="dest-icon" src="http://testserver/static/categories/none.svg"'
            ' alt="Ohne Kategorie" title="Ohne Kategorie">Katharinenhospital</h2>') in page
    assert "<dt>Zu Fuß</dt><dd>1,8 km, ca. 5 Min.</dd>" in page
    assert 'id="map"' in page and 'id="map-data"' in page
    assert "leaflet.js" in page
    assert "Links abbiegen auf Kriegsbergstraße" in page
    assert "openrouteservice" in page
    assert "/foot-walking/" in str(fake_ors.requests[0].url)


def test_map_data_is_safely_embedded(client):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST | {"name": "</script><script>alert(1)</script>"})
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert "</script><script>alert(1)" not in page


def test_routing_error_is_shown(client, fake_ors):
    _setup(client)
    fake_ors.status = 403
    fake_ors.json_body = {"error": "Access disallowed"}
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "foot-walking"}).text
    assert "abgelehnt" in page
    assert 'id="map"' in page  # markers still shown without route


def test_unknown_ids_and_profile(client, fake_ors):
    _setup(client)
    page = client.get("/directions", params={"location_id": 9, "destination_id": 1}).text
    assert "nicht gefunden" in page
    page = client.get("/directions", params={"location_id": "x", "destination_id": 1,
                                             "profile": "rocket"}).text
    assert "/foot-walking/" in str(fake_ors.requests[-1].url)  # unknown profile -> auto


def test_destination_list_links_to_route(client):
    _setup(client)
    assert 'href="/directions?destination_id=1"' in client.get("/destinations").text


def test_directions_language(client, fake_ors):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "lang": "tr"}).text
    assert '<section class="result" lang="tr" dir="ltr">' in page
    assert "<dt>Yürüyerek</dt><dd>1,8 km, yaklaşık 5 dk</dd>" in page
    assert "<dt>Adres</dt>" in page
    assert '<option value="tr" selected>Türkçe (Türkisch)</option>' in page
    assert '<option value="de" >Deutsch</option>' in page  # no "(Deutsch)" duplicate
    assert json.loads(fake_ors.requests[0].content)["language"] == "tr"
    # UI stays German
    assert "Route berechnen" in page


def test_directions_language_rtl_and_iso_mapping(client):
    _setup(client)
    he = client.get("/directions", params={"location_id": 1, "destination_id": 1, "lang": "he"}).text
    assert 'lang="he" dir="rtl"' in he
    ua = client.get("/directions", params={"location_id": 1, "destination_id": 1, "lang": "ua"}).text
    assert 'lang="uk" dir="ltr"' in ua
    assert "1,8 км" in ua


def test_language_names_follow_ui_language(client):
    _setup(client)
    client.cookies.set("ui_lang", "en")
    page = client.get("/directions").text
    assert ">Türkçe (Turkish)</option>" in page
    assert ">Deutsch (German)</option>" in page
    assert ">English</option>" in page
    assert "Euskara" not in page and "Esperanto" not in page


def test_transit_route_is_rendered(client, fake_transit):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "transit"}).text
    assert '<option value="transit" selected>ÖPNV</option>' in page
    assert '<div class="transit-opts" id="transit-opts" >' in page
    assert "max. 2 Umstiege" in page and "Dienstag 09:00" in page
    assert '<details class="transit-details" >' in page  # collapsed by default
    assert "<dt>Mit Bus</dt><dd>28 Min. · Umstiege: 0 · alle 30 Min.</dd>" in page
    assert f"Zu Fuß zur Haltestelle {stop_name('Freibad')}" in page
    assert ">Bus 19</span>" in page and 'Richtung <span class="bidi-isolate">BG Unfallklinik</span>' in page
    assert "Gleis/Steig" not in page.split("Bus 19")[1].split("</li>")[0]
    assert "Weitere Verbindungen" in page and "Hegelstraße" in page
    assert 'href="https://transitous.org/sources/"' in page
    assert "Fahrplanstand:" in page
    assert '"legs": [' in page  # map data


def test_transit_options_from_url_and_print_link(client, fake_transit):
    _setup(client)
    page = client.get("/directions", params=[
        ("location_id", 1), ("destination_id", 1), ("profile", "transit"), ("transit_opts", "1"),
        ("max_transfers", "0"), ("walk_start_min", "10"), ("walk_end_min", "8"),
        ("modes", "bus"), ("weekday", "4"), ("time", "14:30"), ("wheelchair", "1")]).text
    params = fake_transit.requests[0].url.params
    assert params["maxTransfers"] == "0" and params["transitModes"] == "BUS"
    assert params["pedestrianProfile"] == "WHEELCHAIR"
    assert "T14:30:00" in params["time"]
    assert 'name="max_transfers" min="0" max="6" value="0"' in page
    assert "am nächsten Freitag gegen 14:30 Uhr" in page
    assert "Barrierefreiheit laut Fahrplandaten nicht" in page
    assert ("/directions/print?location_id=1&amp;destination_id=1&amp;profile=transit&amp;lang=de"
            "&amp;transit_opts=1&amp;max_transfers=0") in page


def test_transit_option_errors_are_shown(client):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "transit", "transit_opts": "1",
                                             "max_transfers": "42"}).text
    assert "Ungültiger Wert für max_transfers: 42" in page


def test_save_transit_defaults(client, fake_transit):
    _setup(client)
    r = client.post("/directions/transit-defaults", data={
        "location_id": "1", "destination_id": "1", "profile": "transit", "lang": "de",
        "max_transfers": "1", "walk_start_min": "12", "walk_end_min": "6",
        "modes": ["bus", "tram"], "weekday": "2", "time": "10:00"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == ("/directions?location_id=1&destination_id=1&profile=transit"
                                     "&lang=de&saved=1")
    page = client.get(r.headers["location"]).text
    assert "Standardwerte für ÖPNV gespeichert." in page
    assert 'name="walk_start_min" min="1" max="30" value="12"' in page
    assert fake_transit.requests[-1].url.params["transitModes"] == "BUS,TRAM,SUBWAY"


def test_save_transit_defaults_rejects_invalid(client):
    _setup(client)
    r = client.post("/directions/transit-defaults", data={
        "location_id": "1", "destination_id": "1", "profile": "transit", "max_transfers": "x"},
        follow_redirects=False)
    assert "transit_opts=1" in r.headers["location"]
    assert "saved=1" not in r.headers["location"]


def test_transit_error_is_shown(client, fake_transit):
    _setup(client)
    fake_transit.json_body = {"itineraries": []}
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "transit"}).text
    assert "Keine ÖPNV-Verbindung gefunden" in page



def _long_walk(fake_ors, seconds):
    data = json.loads(json.dumps(fake_ors.json_body))
    data["features"][0]["properties"]["summary"]["duration"] = seconds
    fake_ors.json_body = data


def test_modes_offered(client):
    _setup(client)
    page = client.get("/directions").text
    assert '<option value="auto" selected>Automatisch</option>' in page
    assert ">Fahrrad</option>" not in page and ">Auto</option>" not in page


def test_auto_short_walk(client, fake_ors, fake_transit):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert "Automatisch gewählt: zu Fuß – der Fußweg dauert nur 5 Min. (Grenze: 20 Min.)." in page
    assert fake_transit.requests == []
    assert "/directions/print?location_id=1&amp;destination_id=1&amp;profile=foot-walking" in page


def test_auto_long_walk_uses_transit(client, fake_ors, fake_transit):
    _setup(client)
    _long_walk(fake_ors, 50 * 60)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert "Automatisch gewählt: ÖPNV – 28 Min. statt 50 Min. zu Fuß." in page
    assert "<dt>Mit Bus</dt>" in page
    assert "profile=transit&amp;lang=de&amp;transit_opts=1" in page


def test_auto_transit_not_faster(client, fake_ors, fake_transit):
    _setup(client)
    _long_walk(fake_ors, 25 * 60)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert "mit Bus und Bahn nicht schneller (28 statt 25 Min.)" in page
    assert "<dt>Zu Fuß</dt>" in page


def test_auto_threshold_from_options(client, fake_ors, fake_transit):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "transit_opts": "1", "auto_walk_max_min": "5",
                                             "modes": "bus"}).text
    assert "(Grenze: 5 Min.)" in page   # 5 min walk is still within the limit
    assert 'name="auto_walk_max_min" min="5" max="60" value="5"' in page


def test_auto_no_transit_connection(client, fake_ors, fake_transit):
    _setup(client)
    _long_walk(fake_ors, 50 * 60)
    fake_transit.json_body = {"itineraries": []}
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1}).text
    assert "keine ÖPNV-Verbindung verfügbar (Keine ÖPNV-Verbindung gefunden." in page
    assert "<dt>Zu Fuß</dt>" in page


def test_bicycle_falls_back_to_auto(client, fake_ors):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "cycling-regular"}).text
    assert all("/cycling-regular/" not in str(r.url) for r in fake_ors.requests)
    assert '<option value="auto" selected>' in page
