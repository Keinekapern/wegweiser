import pytest

from app import db
from app.services import line_symbols
from app.services.transit import Alternative, TransitLeg, TransitPlan


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "sym.sqlite")
    db.migrate(c)
    yield c
    c.close()


def _leg(line, lat=48.52, lon=9.05, mode="BUS"):
    return TransitLeg(kind="transit", mode=mode, from_name="A", to_name="B", duration_s=60,
                      line=line, from_lat=lat, from_lon=lon)


def _plan(legs, alternatives=()):
    return TransitPlan(profile="transit", duration_s=60, transfers=0, headway_min=None,
                       legs=legs, alternatives=list(alternatives))


def test_tuebingen_set_is_seeded(conn):
    (s,) = db.list_line_symbol_sets(conn)
    assert s.name == "TüBus Tübingen"
    assert len(s.symbols) == 26
    assert s.symbols["1"][0] == "Katze"
    assert s.symbols["35"] == ("Lokomotive", "symbols/locomotive.svg")


def test_seeded_images_exist():
    from pathlib import Path
    static = Path(__file__).parent.parent / "app" / "static"
    import sqlite3, tempfile
    c = db.connect(Path(tempfile.mkdtemp()) / "x.sqlite")
    db.migrate(c)
    for _label, image in db.list_line_symbol_sets(c)[0].symbols.values():
        assert (static / image).is_file(), image


def test_attach_symbol_inside_area(conn):
    plan = _plan([_leg("19"), _leg("5")])
    credits = line_symbols.attach(conn, plan)
    assert plan.legs[0].symbol == {"label": "Brief", "image": "symbols/letter.svg"}
    assert plan.legs[1].symbol["label"] == "Kreuz"
    assert credits == []   # own drawings, no attribution needed


@pytest.mark.parametrize("leg", [
    _leg("19", lat=48.77, lon=9.18),   # Stuttgart: outside the area
    _leg("19", mode="TRAM"),           # wrong mode
    _leg("20"),                        # line without symbol
    _leg("X1"),
])
def test_no_symbol(conn, leg):
    plan = _plan([leg])
    assert line_symbols.attach(conn, plan) == []
    assert plan.legs[0].symbol is None


def test_alternatives_get_symbols(conn):
    alt = Alternative(line_summary=[("BUS", "8"), ("BUS", "99")], board_stop="Hbf",
                      headway_min=30, duration_s=60, board_lat=48.51, board_lon=9.05)
    plan = _plan([_leg("19")], [alt])
    line_symbols.attach(conn, plan)
    assert plan.alternatives[0].symbols[0]["label"] == "Tasse"
    assert plan.alternatives[0].symbols[1] is None


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
            "style=\"--symbol: url('http://testserver/static/symbols/letter.svg')\"></span>"
            in page)
    # alternative Bus 5: own single-colour symbol, drawn as a mask in the text colour
    assert ('<span class="line-symbol mono" role="img" aria-label="Kreuz" title="Kreuz" '
            "style=\"--symbol: url('http://testserver/static/symbols/cross-roof.svg')\"></span>"
            in page)
    assert '<span class="line-badge small" style="--line-color: #58102f; --line-text: #fff">' in page.replace(' on-dark', '')
    assert "Twemoji" not in page
    printout = client.get("/directions/print", params=params).text
    assert 'aria-label="Brief"' in printout
    assert "Twemoji" not in printout
