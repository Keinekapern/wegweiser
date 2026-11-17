from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import db
from app.i18n import Msg
from app.services.transit import (TransitError, TransitSettings, decode_polyline,
                                  headway_minutes, load_defaults, reference_datetime,
                                  save_defaults, summarize)
from tests.conftest import FakeNominatim, encode_polyline, make_transit, make_transit_sample

START = (48.77, 9.18)
END = (48.784, 9.171)
TODAY = date(2026, 11, 15)  # Sunday


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "transit.sqlite")
    db.migrate(c)
    yield c
    c.close()


def test_decode_polyline_google_example():
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert pts == [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]


def test_encode_decode_roundtrip():
    coords = [[48.770001, 9.180002], [48.784, 9.171]]
    assert decode_polyline(encode_polyline(coords)) == coords


def _dt(h, m):
    return datetime(2026, 11, 17, h, m, tzinfo=timezone.utc)


def test_headway():
    assert headway_minutes([_dt(8, 0), _dt(8, 30), _dt(9, 0)]) == 30
    assert headway_minutes([_dt(8, 0), _dt(8, 58), _dt(10, 1)]) == 60
    assert headway_minutes([_dt(8, 0), _dt(8, 9), _dt(8, 21)]) == 10
    assert headway_minutes([_dt(8, 0)]) is None


def test_summarize_picks_fastest_direct_pattern():
    plan = summarize(make_transit_sample(), wheelchair=False)
    rides = [leg for leg in plan.legs if leg.kind == "transit"]
    assert [r.line for r in rides] == ["19"]
    assert rides[0].headsign == "BG Unfallklinik"
    assert rides[0].from_name == "Freibad" and rides[0].to_name == "Uni-Kliniken Berg"
    assert rides[0].color == "#58102f"
    assert plan.transfers == 0
    assert plan.duration_s == 28 * 60
    assert plan.headway_min == 30
    assert [l.kind for l in plan.legs] == ["walk", "transit", "walk"]
    assert plan.legs[0].geometry[0] == [48.77, 9.18]
    # alternatives: Bus 5 (every 30 min), then the one with a transfer
    assert plan.alternatives[0].line_summary == [("BUS", "5")]
    assert plan.alternatives[0].board_stop == "Hegelstraße"
    assert plan.alternatives[0].headway_min == 30
    assert plan.alternatives[0].colors == ["#58102f"]
    assert plan.alternatives[1].line_summary == [("BUS", "8"), ("BUS", "13")]
    assert plan.alternatives[1].headway_min is None
    assert not plan.wheelchair_issue


def test_summarize_wheelchair_flag():
    assert summarize(make_transit_sample(), wheelchair=True).wheelchair_issue


def test_summarize_no_connection():
    with pytest.raises(TransitError, match="Keine ÖPNV-Verbindung"):
        summarize({"itineraries": []}, wheelchair=False)


def test_invalid_route_color_is_dropped():
    data = make_transit_sample()
    for it in data["itineraries"]:
        for leg in it["legs"]:
            if leg["mode"] != "WALK":
                leg["routeColor"] = "red;x"
    plan = summarize(data, wheelchair=False)
    assert all(l.color is None for l in plan.legs)


def test_settings_parse():
    s = TransitSettings.parse({"max_transfers": "1", "walk_start_min": "10", "walk_end_min": "5",
                               "modes": ["bus", "train"], "wheelchair": "1", "weekday": "4",
                               "time": "7:30"})
    assert (s.max_transfers, s.walk_start_min, s.walk_end_min) == (1, 10, 5)
    assert s.modes == ["bus", "train"] and s.wheelchair and s.weekday == 4 and s.time == "07:30"


def test_settings_parse_invalid_values_fall_back():
    errors: list[Msg] = []
    s = TransitSettings.parse({"max_transfers": "99", "walk_start_min": "x", "modes": [],
                               "weekday": "9", "time": "25:00"}, errors)
    assert s == TransitSettings()
    assert len(errors) == 5


def test_defaults_roundtrip(conn):
    assert load_defaults(conn) == TransitSettings()
    save_defaults(conn, TransitSettings(max_transfers=0, modes=["bus"]))
    assert load_defaults(conn).max_transfers == 0
    assert load_defaults(conn).modes == ["bus"]


def test_reference_datetime_is_next_weekday_from_tomorrow():
    tz = ZoneInfo("Europe/Berlin")
    ref = reference_datetime(TransitSettings(weekday=1, time="09:00"), TODAY, tz)
    assert ref.isoformat() == "2026-11-17T09:00:00+01:00"
    # same weekday as today -> next week
    ref = reference_datetime(TransitSettings(weekday=6, time="09:00"), TODAY, tz)
    assert ref.date() == date(2026, 11, 22)


def test_request_parameters(conn):
    fake = FakeNominatim(json_body=make_transit_sample())
    settings = TransitSettings(max_transfers=1, walk_start_min=10, walk_end_min=5,
                               modes=["bus", "train"], wheelchair=True, weekday=1, time="09:00")
    make_transit(fake).plan(conn, START, END, settings, language="ua", today=TODAY)
    req = fake.requests[0]
    assert req.url.path == "/api/v6/plan"
    assert req.headers["User-Agent"] == "Wegweiser/test (test@example.org)"
    p = req.url.params
    assert p["fromPlace"] == "48.77,9.18" and p["toPlace"] == "48.784,9.171"
    assert p["time"] == "2026-11-17T09:00:00+01:00"
    assert p["maxTransfers"] == "1"
    assert p["maxPreTransitTime"] == "600" and p["maxPostTransitTime"] == "300"
    assert p["transitModes"] == "BUS,SUBURBAN,REGIONAL_RAIL"
    assert p["directModes"] == ""
    assert p["pedestrianProfile"] == "WHEELCHAIR"
    assert p["language"] == "uk"


def test_plan_is_cached_and_counted(conn):
    fake = FakeNominatim(json_body=make_transit_sample())
    client = make_transit(fake)
    s = TransitSettings()
    assert client.plan(conn, START, END, s, today=TODAY)[1] is False
    plan, cached = client.plan(conn, START, END, s, today=TODAY)
    assert cached and plan.headway_min == 30
    client.plan(conn, START, END, TransitSettings(max_transfers=0), today=TODAY)
    assert len(fake.requests) == 2
    assert db.usage_today(conn, "transitous-plan") == 2


def test_requires_contact(conn):
    fake = FakeNominatim(json_body=make_transit_sample())
    with pytest.raises(TransitError, match="APP_CONTACT"):
        make_transit(fake, has_contact=False).plan(conn, START, END, TransitSettings())
    assert fake.requests == []


def test_daily_limit(conn):
    fake = FakeNominatim(json_body=make_transit_sample())
    client = make_transit(fake, daily_limit=1)
    client.plan(conn, START, END, TransitSettings(), today=TODAY)
    with pytest.raises(TransitError, match="Tageslimit"):
        client.plan(conn, START, END, TransitSettings(max_transfers=0), today=TODAY)


@pytest.mark.parametrize("status", [400, 429, 500])
def test_http_errors_not_cached(conn, status):
    client = make_transit(FakeNominatim(status=status, json_body={"error": "nope"}))
    with pytest.raises(TransitError, match="fehlgeschlagen"):
        client.plan(conn, START, END, TransitSettings())
    assert conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0] == 0


def test_network_error(conn):
    client = make_transit(FakeNominatim())
    client._http = httpx.Client(transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    with pytest.raises(TransitError, match="nicht erreichbar"):
        client.plan(conn, START, END, TransitSettings())


def test_malformed_response(conn):
    client = make_transit(FakeNominatim(json_body={"itineraries": [{"legs": [{"mode": "BUS"}]}]}))
    with pytest.raises(TransitError, match="unerwartet"):
        client.plan(conn, START, END, TransitSettings())


def test_text_color_for_contrast():
    from app.services.transit import text_color_for
    assert text_color_for("#9995c9") == "#000"   # light purple (Bus 18) -> black text
    assert text_color_for("#58102f") == "#fff"   # dark red (Bus 5) -> white text
    assert text_color_for("#ffff00") == "#000"
    assert text_color_for(None) == "#fff"


def test_same_place_names_drop_shared_municipality():
    from app.services.transit import same_place_names

    assert same_place_names("Tübingen Freibad", "Tübingen BG Unfallklinik") == ("Freibad", "BG Unfallklinik")
    assert same_place_names("Bad Urach Bahnhof", "Bad Urach Kurhaus") == ("Bahnhof", "Kurhaus")
    assert same_place_names("Tübingen, Freibad", "Tübingen, Hbf") == ("Freibad", "Hbf")


def test_same_place_names_keep_names_otherwise():
    from app.services.transit import same_place_names

    # different places
    assert same_place_names("Tübingen Hbf", "Reutlingen ZOB") == ("Tübingen Hbf", "Reutlingen ZOB")
    # "Bad" alone is not a place
    assert same_place_names("Bad Urach Bahnhof", "Bad Boll Kurhaus") == ("Bad Urach Bahnhof", "Bad Boll Kurhaus")
    # nothing would be left of a name
    assert same_place_names("Tübingen", "Tübingen Freibad") == ("Tübingen", "Tübingen Freibad")
    assert same_place_names("Freibad", "Hbf") == ("Freibad", "Hbf")


def test_municipality_from_address():
    from app.services.transit import common_place, municipality

    assert municipality("Schnarrenbergstraße 95, 72076 Tübingen") == "Tübingen"
    assert municipality("Beispielweg 1, 71065 Sindelfingen (Stadt)") == "Sindelfingen"
    assert municipality("Hauptstraße 1, 72574 Bad Urach") == "Bad Urach"
    assert municipality("irgendwo") is None
    assert common_place("A 1, 72072 Tübingen", "B 2, 72076 Tübingen") == "Tübingen"
    assert common_place("A 1, 72072 Tübingen", "B 2, 71065 Sindelfingen (Stadt)") is None


def test_strip_place():
    from app.services.transit import strip_place

    assert strip_place("Tübingen Freibad", "Tübingen") == "Freibad"
    assert strip_place("Tübingen, Freibad", "Tübingen") == "Freibad"
    assert strip_place("Bad Urach Kurhaus", "Bad Urach") == "Kurhaus"
    # other places, other words starting with the same letters, nothing left
    assert strip_place("Reutlingen ZOB", "Tübingen") == "Reutlingen ZOB"
    assert strip_place("Tübinger Straße", "Tübingen") == "Tübinger Straße"
    assert strip_place("Tübingen", "Tübingen") == "Tübingen"
    assert strip_place("Tübingen Freibad", None) == "Tübingen Freibad"


def test_without_place_shortens_all_names_but_keeps_the_original():
    from app.services.transit import Alternative, TransitLeg, TransitPlan, without_place

    plan = TransitPlan("transit", 1800, 0, 30, [
        TransitLeg("walk", "WALK", "START", "Tübingen Freibad", 480),
        TransitLeg("transit", "BUS", "Tübingen Freibad", "Tübingen BG Unfallklinik", 1080,
                   line="19", headsign="Tübingen BG Unfallklinik"),
        TransitLeg("walk", "WALK", "Tübingen BG Unfallklinik", "END", 240),
    ], [Alternative([("BUS", "18")], "Tübingen Hegelstraße", 30, 1900)])
    short = without_place(plan, "Tübingen")
    ride = short.legs[1]
    assert (ride.from_name, ride.to_name, ride.headsign) == ("Freibad", "BG Unfallklinik", "BG Unfallklinik")
    assert short.legs[0].to_name == "Freibad" and short.alternatives[0].board_stop == "Hegelstraße"
    assert plan.legs[1].from_name == "Tübingen Freibad"   # cached plan untouched


def test_stop_sign_depends_on_the_mode():
    from app.deps import stop_name
    from app.services.transit import stop_icon

    assert stop_icon("BUS") == stop_icon("TRAM") == stop_icon("COACH") == "stop.svg"
    assert stop_icon("SUBWAY") == "stop-metro.svg"
    assert stop_icon("SUBURBAN") == stop_icon("HIGHSPEED_RAIL") == "stop-train.svg"
    assert stop_icon("FERRY") == "stop-ferry.svg" and stop_icon("AERIAL_LIFT") == "stop-cable.svg"
    assert stop_icon(None) == stop_icon("OTHER") == "stop.svg"
    assert 'src="/static/stop-train.svg"' in stop_name("Hauptbahnhof", "REGIONAL_RAIL")


def test_map_data_carries_the_stop_sign(client, fake_transit):
    import json

    client.post("/locations", data={"name": "EA", "address": "a", "lat": "48.77", "lon": "9.17"})
    client.post("/destinations", data={"name": "Klinik", "address": "y", "lat": "48.78",
                                       "lon": "9.17", "phone": "", "website": "",
                                       "opening_hours": "", "google_maps_url": "", "note": "",
                                       "osm_type": "", "osm_id": ""})
    page = client.get("/directions", params={"location_id": 1, "destination_id": 1,
                                             "profile": "transit"}).text
    data = json.loads(page.split('<script id="map-data" type="application/json">')[1].split("</script>")[0])
    assert {leg["stop_icon"] for leg in data["route"]["legs"]} == {"/static/stop.svg"}


def _leg(mode, frm, to, frm_id="", to_id=""):
    return {"mode": mode, "from": {"name": frm, "stopId": frm_id}, "to": {"name": to, "stopId": to_id}}


def test_walks_within_a_station_are_dropped():
    from app.services.transit import drop_station_transfers

    legs = [
        _leg("WALK", "START", "Freibad"),
        _leg("BUS", "Freibad", "Tübingen Hauptbahnhof", to_id="de-DELFI_de:08416:11000:1:2"),
        # same station, other platform (DHID differs only after the 3rd part)
        _leg("WALK", "Tübingen Hauptbahnhof", "Tübingen Hbf (Gleis 13)",
             "de-DELFI_de:08416:11000:1:2", "de-DELFI_de:08416:11000:3:13"),
        _leg("REGIONAL_RAIL", "Tübingen Hbf (Gleis 13)", "Herrenberg"),
        _leg("WALK", "Herrenberg", "Herrenberg"),                      # same name
        _leg("SUBURBAN", "Herrenberg", "Böblingen"),
        _leg("WALK", "Böblingen", "Böblingen Keilbergstraße",          # real walk: kept
             "de-DELFI_de:08115:1:1:1", "de-DELFI_de:08115:2:1:1"),
        _leg("BUS", "Böblingen Keilbergstraße", "Klinik"),
        _leg("WALK", "Klinik", "END"),
    ]
    kept = drop_station_transfers(legs)
    assert [l["mode"] for l in kept] == ["WALK", "BUS", "REGIONAL_RAIL", "SUBURBAN", "WALK", "BUS", "WALK"]


def test_trip_numbers_are_removed_from_line_names():
    from app.services.transit import _line

    assert _line({"displayName": "RB63 (22757)"}) == "RB63"
    assert _line({"displayName": "S1"}) == "S1"
    assert _line({"routeShortName": "Bus 721"}) == "Bus 721"


def test_short_rides_are_ranked_down():
    from app.services.transit import summarize

    def itin(duration, legs, transfers):
        return {"duration": duration, "transfers": transfers, "startTime": "2026-11-17T09:00:00Z",
                "legs": [{"mode": m, "duration": d, "routeShortName": line, "headsign": "X",
                          "startTime": "2026-11-17T09:00:00Z",
                          "from": {"name": f, "lat": 48.5, "lon": 9.0}, "to": {"name": t, "lat": 48.5, "lon": 9.0},
                          "legGeometry": {"points": "", "precision": 6}}
                         for m, d, line, f, t in legs]}
    hop = itin(88 * 60, [("WALK", 600, "", "START", "A"), ("BUS", 50, "8", "A", "B"),
                         ("WALK", 480, "", "B", "Hbf"), ("REGIONAL_RAIL", 1800, "RB63", "Hbf", "Z"),
                         ("WALK", 60, "", "Z", "END")], 1)
    direct = itin(91 * 60, [("WALK", 480, "", "START", "C"), ("BUS", 300, "19", "C", "Hbf"),
                            ("REGIONAL_RAIL", 1800, "RB63", "Hbf", "Z"), ("WALK", 60, "", "Z", "END")], 1)
    plan = summarize({"itineraries": [hop, direct]}, wheelchair=False)
    assert [leg.line for leg in plan.legs if leg.kind == "transit"] == ["19", "RB63"]
    assert plan.alternatives[0].line_summary[0] == ("BUS", "8")


def test_strip_place_with_town_additions():
    from app.services.transit import strip_place

    assert strip_place("Freiburg, Paduaallee", "Freiburg im Breisgau") == "Paduaallee"
    assert strip_place("Freiburg im Breisgau Hbf", "Freiburg im Breisgau") == "Hbf"
    assert strip_place("Frankfurt (Main) Hbf", "Frankfurt am Main") == "Frankfurt (Main) Hbf"
    assert strip_place("Freiburger Straße", "Freiburg im Breisgau") == "Freiburger Straße"
