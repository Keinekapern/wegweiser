"""Line symbols and colours from regional add-ons (app/regions/), mode colours as fallback."""

import json

import pytest

from app import regions
from app.services import line_symbols
from app.services.transit import Alternative, TransitLeg, TransitPlan, fallback_color


@pytest.fixture(autouse=True)
def all_regions(monkeypatch):
    monkeypatch.delenv("REGIONS", raising=False)
    regions._active.cache_clear()
    yield
    regions._active.cache_clear()


def _leg(line, lat=48.52, lon=9.05, mode="BUS", color=None):
    return TransitLeg(kind="transit", mode=mode, from_name="A", to_name="B", duration_s=60,
                      line=line, from_lat=lat, from_lon=lon, color=color)


def _plan(legs, alternatives=()):
    return TransitPlan(profile="transit", duration_s=60, transfers=0, headway_min=None,
                       legs=legs, alternatives=list(alternatives))


def test_tuebingen_add_on_is_installed():
    (r,) = regions.active()
    assert r.key == "tuebingen" and r.name == "TüBus Tübingen"
    assert len(r.symbols) == 26 and r.symbols["1"] == ("Katze", "tuebingen/symbols/cat.svg")
    assert r.colors["5"] == "#62052f" and r.colors["18"] == "#a297c6"


def test_attach_symbol_and_colour_inside_area():
    plan = _plan([_leg("19", color="#000000"), _leg("5"), _leg("18")])
    assert line_symbols.attach(None, plan) == []          # own drawings, no credit
    assert plan.legs[0].symbol == {"label": "Brief", "image": "tuebingen/symbols/letter.svg",
                                   "mono": True}
    assert plan.legs[0].color == "#611e82"                # network map beats the timetable
    assert plan.legs[1].symbol["label"] == "Kreuz" and plan.legs[1].color == "#62052f"
    assert plan.legs[2].color == "#a297c6"                # subcontractor line, no symbol


@pytest.mark.parametrize("leg, color", [
    (_leg("19", lat=48.77, lon=9.18), fallback_color("BUS")),      # Stuttgart: outside the area
    (_leg("19", mode="TRAM"), fallback_color("TRAM")),              # wrong mode
    (_leg("X1"), fallback_color("BUS")),
    (_leg("X1", color="#123456"), "#123456"),                       # timetable colour kept
])
def test_no_symbol_outside(leg, color):
    plan = _plan([leg])
    line_symbols.attach(None, plan)
    assert plan.legs[0].symbol is None and plan.legs[0].color == color


def test_mode_colours_after_db_signage():
    assert fallback_color("SUBURBAN") == "#587f40"
    assert fallback_color("SUBWAY") == "#005a8c"
    assert fallback_color("TRAM") == "#bb1e10"
    assert fallback_color("BUS") == "#992572"
    assert fallback_color("REGIONAL_RAIL") == fallback_color(None) == "#222d5a"


def test_alternatives_get_symbols_and_colours():
    alt = Alternative(line_summary=[("BUS", "8"), ("BUS", "99")], board_stop="Hbf",
                      headway_min=30, duration_s=60, board_lat=48.51, board_lon=9.05)
    line_symbols.attach(None, _plan([_leg("19")], [alt]))
    assert alt.symbols[0]["label"] == "Tasse" and alt.symbols[1] is None
    assert alt.colors == ["#6a8dc1", fallback_color("BUS")]


def test_regions_can_be_left_out(monkeypatch):
    monkeypatch.setenv("REGIONS", "none")
    plan = _plan([_leg("19")])
    line_symbols.attach(None, plan)
    assert regions.active() == () and plan.legs[0].symbol is None
    assert plan.legs[0].color == fallback_color("BUS")
    monkeypatch.setenv("REGIONS", "tuebingen,berlin")      # unknown key: warning, ignored
    assert [r.key for r in regions.active()] == ["tuebingen"]


def test_broken_region_file(tmp_path):
    d = tmp_path / "x"
    (d / "symbols").mkdir(parents=True)
    (d / "region.json").write_text(json.dumps({"name": "X", "area": {"min_lat": 0, "min_lon": 0,
                                   "max_lat": 1, "max_lon": 1}, "lines": {"1": {"color": "red"}}}))
    with pytest.raises(ValueError, match="#rrggbb"):
        regions.load(d)


def test_symbols_rendered_on_page_and_printout(client, fake_transit):
    # move the sample connection to Tübingen
    moved = set()
    for it in fake_transit.json_body["itineraries"]:
        for leg in it["legs"]:
            for p in (leg["from"], leg["to"]):
                if id(p) not in moved:  # place objects may be shared between legs
                    moved.add(id(p))
                    p["lat"], p["lon"] = p["lat"] - 0.25, p["lon"] - 0.13
    client.post("/locations", data={"name": "EA", "address": "x", "lat": "48.52", "lon": "9.05"})
    client.post("/destinations", data={"name": "Klinik", "address": "y", "lat": "48.53",
                                       "lon": "9.04", "phone": "", "website": "",
                                       "opening_hours": "", "google_maps_url": "", "note": "",
                                       "osm_type": "", "osm_id": ""})
    params = {"location_id": 1, "destination_id": 1, "profile": "transit"}
    page = client.get("/directions", params=params).text
    assert ('<span class="line-symbol mono" role="img" aria-label="Brief" title="Brief" '
            "style=\"--symbol: url('http://testserver/regions/tuebingen/symbols/letter.svg')\"></span>"
            in page)
    # alternative Bus 5 in the network-map colour
    assert '<span class="line-badge small" style="--line-color: #62052f; --line-text: #fff">' in page.replace(' on-dark', '')
    assert client.get("/regions/tuebingen/symbols/letter.svg").status_code == 200
    printout = client.get("/directions/print", params=params).text
    assert 'aria-label="Brief"' in printout
