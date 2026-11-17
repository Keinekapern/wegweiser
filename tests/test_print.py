import re
from urllib.parse import parse_qs, urlsplit

from app.db import Destination
from app.services.qr import apple_url, google_url, map_links, osm_url, qr_svg

from tests.test_directions import DEST, LOC
from app.deps import stop_name


def _dest(**kw):
    base = dict(id=1, name="Katharinenhospital", address="Kriegsbergstraße 60, 70174 Stuttgart",
                lat=48.7837421, lon=9.1733168)
    return Destination(**(base | kw))


def test_google_url_search_fallback():
    url = google_url(_dest())
    parts = urlsplit(url)
    assert parts.netloc == "www.google.com" and parts.path == "/maps/search/"
    assert parse_qs(parts.query) == {
        "api": ["1"], "query": ["Katharinenhospital, Kriegsbergstraße 60, 70174 Stuttgart"]}


def test_google_url_prefers_verified_link():
    assert google_url(_dest(google_maps_url="https://maps.app.goo.gl/abc")) == \
        "https://maps.app.goo.gl/abc"


def test_osm_and_apple_urls():
    assert osm_url(_dest()) == ("https://www.openstreetmap.org/?mlat=48.783742&mlon=9.173317"
                                "#map=18/48.783742/9.173317")
    parts = urlsplit(apple_url(_dest(name="Café & Co")))
    assert parts.netloc == "maps.apple.com" and parts.path == "/place"
    assert parse_qs(parts.query) == {"coordinate": ["48.783742,9.173317"], "name": ["Café & Co"]}


def test_qr_svg_is_scalable_inline_svg():
    svg = qr_svg("https://example.org")
    assert svg.startswith("<svg viewBox=")
    assert "width=" not in svg.split(">")[0]


def test_map_links():
    links = map_links(_dest(), "Apple Karten")
    assert [l.key for l in links] == ["google", "osm", "apple"]
    assert links[2].label == "Apple Karten"
    assert all(l.svg.startswith("<svg") for l in links)


def _setup(client):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST | {"phone": "+49 711 27801", "opening_hours": "24/7"})


def test_print_view(client):
    _setup(client)
    r = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                "profile": "foot-walking"})
    assert r.status_code == 200
    page = r.text
    assert "<title>Katharinenhospital</title>" in page
    assert '<html lang="de" dir="ltr">' in page
    assert "<h1>Katharinenhospital</h1>" in page
    assert "Zu Fuß:</strong> 1,8 km, ca. 5 Min." in page
    assert "+49 711 27801" in page and "24/7" in page
    assert page.count('<svg viewBox=') == 3
    assert "Google Maps" in page and "OpenStreetMap" in page and "Apple Karten" in page
    assert "© OpenStreetMap-Mitwirkende (ODbL)" in page
    assert "openrouteservice.org (HeiGIT)" in page
    assert re.search(r"Erstellt am \d\d\.\d\d\.\d{4}", page)
    assert "Links abbiegen auf Kriegsbergstraße" in page
    assert 'id="print-button" disabled' in page
    assert "print.js" in page and "leaflet.js" in page
    assert 'href="/directions?location_id=1&amp;destination_id=1&amp;profile=foot-walking&amp;lang=de"' in page


def test_print_view_in_other_language_with_english_ui(client):
    _setup(client)
    client.cookies.set("ui_lang", "en")
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "lang": "fr"}).text
    assert '<html lang="fr" dir="ltr">' in page
    assert "<strong>À pied:</strong>" in page
    assert "Apple Plans" in page and "Sources:" in page
    assert "Scannez avec votre téléphone" in page
    assert ">Print</button>" in page  # toolbar in UI language
    assert '<div class="toolbar" lang="en" dir="ltr">' in page


def test_print_view_rtl(client):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "lang": "he"}).text
    assert '<html lang="he" dir="rtl">' in page
    assert '<dd dir="ltr">+49 711 27801</dd>' in page


def test_print_view_without_route_still_renders(client, fake_ors):
    _setup(client)
    fake_ors.status = 500
    fake_ors.json_body = {"error": "boom"}
    r = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                 "profile": "foot-walking"})
    assert r.status_code == 200
    assert 'class="error"' in r.text
    assert page_has_no_steps(r.text)


def page_has_no_steps(page):
    return 'class="steps"' not in page


def test_print_view_requires_destination(client):
    _setup(client)
    r = client.get("/directions/print", params={"location_id": 1})
    assert r.status_code == 404
    r = client.get("/directions/print", params={"location_id": 1, "destination_id": 99})
    assert r.status_code == 404
    assert "nicht gefunden" in r.text


def test_directions_page_links_to_print_view(client):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "lang": "tr"}).text
    assert 'href="/directions/print?location_id=1&amp;destination_id=1&amp;profile=foot-walking&amp;lang=tr"' in page


def test_print_view_transit(client, fake_transit):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "profile": "transit", "lang": "en"}).text
    assert "<strong>By bus:</strong> 28 min · Transfers: 0 · every 30 min" in page
    assert f"Walk to stop {stop_name('Freibad')}" in page and 'towards <span class="bidi-isolate">BG Unfallklinik</span>' in page
    # stop sign before stop names, not before the line destination
    assert "towards <span class=\"stop-name\">" not in page
    assert "Timetable data: Transitous (transitous.org/sources)" in page
    assert "Timetable as of" in page
    assert 'id="toggle-steps"' in page            # walking steps to/from the stops
    assert 'id="toggle-insets" checked' in page


def test_print_view_has_bw_toggle(client):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1}).text
    assert 'id="toggle-bw"' in page and "Für Schwarz-Weiß-Druck optimieren" in page


def test_print_view_tigrinya_and_fonts(client):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "lang": "ti"}).text
    assert '<html lang="ti" dir="ltr">' in page
    assert "ብእግሪ" in page and "fonts.css" in page
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "lang": "fa"}).text
    assert '<html lang="fa" dir="rtl">' in page


def test_print_view_has_orientation_select(client):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1}).text
    assert 'id="orientation"' in page and 'id="page-style"' in page
    assert 'id="sheet2" hidden' in page


def test_vendored_fonts_exist():
    from pathlib import Path
    import re
    static = Path(__file__).parent.parent / "app" / "static"
    css = (static / "fonts.css").read_text()
    for url in re.findall(r'url\("([^"]+)"\)', css):
        assert (static / url).is_file(), url


def test_ride_arrow_follows_reading_direction(client, fake_transit):
    _setup(client)
    params = {"location_id": 1, "destination_id": 1, "profile": "transit"}
    ltr = client.get("/directions/print", params=params | {"lang": "en"}).text
    rtl = client.get("/directions/print", params=params | {"lang": "ar"}).text
    assert f"→ {stop_name('Uni-Kliniken Berg')}" in ltr
    # right-to-left: names are isolated, the arrow points in reading direction
    assert f"← {stop_name('Uni-Kliniken Berg')}" in rtl and "→ <span" not in rtl
