import json

from tests.test_directions import DEST, LOC
from app.deps import stop_name


def _setup(client):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST)


def _transit(client, **params):
    return client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "transit"} | params).text


def _map_data(page):
    raw = page.split('<script id="map-data" type="application/json">')[1].split("</script>")[0]
    return json.loads(raw)


def test_walk_details_for_first_and_last_walk(client, fake_ors):
    _setup(client)
    page = _transit(client)
    details = _map_data(page)["walk_details"]
    assert [d["kind"] for d in details] == ["to_stop", "to_dest"]
    assert details[0]["start"]["name"] == "Büro Mitte" and details[0]["end"]["name"] == "Freibad"
    assert details[1]["start"]["name"] == "Uni-Kliniken Berg"
    assert details[1]["end"]["name"] == "Katharinenhospital"
    # re-routed with openrouteservice on foot (geometry from the ORS sample)
    foot = [r for r in fake_ors.requests if "/foot-walking/" in str(r.url)]
    assert len(foot) == 2
    assert details[0]["geometry"][0] == [48.77, 9.18]
    assert page.count('class="inset-map"') == 2
    # duration from the timetable (8 min), distance from openrouteservice (1.8 km)
    assert f"Zu Fuß zur Haltestelle {stop_name('Freibad')}" in page and "(8 Min., 1,8 km)" in page
    assert "Links abbiegen auf Kriegsbergstraße" in page   # walking steps (collapsed)


def test_walk_details_fall_back_to_transit_geometry(client, fake_ors):
    _setup(client)
    fake_ors.status = 500
    fake_ors.json_body = {"error": "boom"}
    page = _transit(client)
    details = _map_data(page)["walk_details"]
    assert len(details) == 2
    assert details[0]["geometry"] == [[48.77, 9.18], [48.775, 9.176]]   # Transitous walk
    assert "walk-steps" not in page


def test_no_walk_details_for_other_modes(client):
    _setup(client)
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "foot-walking"}).text
    assert _map_data(page)["walk_details"] == []
    assert 'class="inset-map"' not in page


def test_print_view_has_insets(client):
    _setup(client)
    page = client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "profile": "transit", "lang": "tr"}).text
    assert page.count('class="inset-map"') == 2
    assert f"{stop_name('Freibad')} durağına yürüyün" in page and "Varış noktasına yürüyün" in page
    assert 'id="toggle-insets" checked' in page
