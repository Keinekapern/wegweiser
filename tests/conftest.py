import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.geocoding import NominatimClient, get_geocoder
from app.services.ratelimit import RateLimiter
from app.services.routing import OrsClient, get_router
from app.services.transit import TransitousClient, get_transit

SAMPLE_RESULT = {
    "place_id": 1,
    "osm_type": "way",
    "osm_id": 4711,
    "lat": "48.7840",
    "lon": "9.1710",
    "category": "amenity",
    "type": "hospital",
    "name": "Katharinenhospital",
    "display_name": "Katharinenhospital, Kriegsbergstraße 60, Stuttgart, 70174, Deutschland",
    "address": {"amenity": "Katharinenhospital", "road": "Kriegsbergstraße",
                "house_number": "60", "postcode": "70174", "city": "Stuttgart"},
    "extratags": {"phone": "+49 711 27801", "website": "https://www.klinikum-stuttgart.de",
                  "opening_hours": "24/7"},
    "namedetails": {"name": "Katharinenhospital"},
}


class FakeNominatim:
    """Fake upstream API (Nominatim or ORS): records requests and answers with a canned response."""

    def __init__(self, status=200, json_body=None):
        self.status = status
        self.json_body = [SAMPLE_RESULT] if json_body is None else json_body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.json_body)


def make_client(fake: FakeNominatim, **kwargs) -> NominatimClient:
    return NominatimClient(
        base_url="https://nominatim.test",
        user_agent="Wegweiser/test",
        countrycodes="de",
        rate_limiter=kwargs.pop("rate_limiter", RateLimiter(0)),
        transport=httpx.MockTransport(fake),
        **kwargs,
    )


SAMPLE_ROUTE = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {"type": "LineString",
                     "coordinates": [[9.18, 48.77], [9.175, 48.78], [9.171, 48.784]]},
        "properties": {
            "summary": {"distance": 1834.2, "duration": 312.5},
            "segments": [{"distance": 1834.2, "duration": 312.5, "steps": [
                {"distance": 800.0, "duration": 120.0, "instruction": "Nach Norden auf Hauptstraße"},
                {"distance": 1034.2, "duration": 192.5, "instruction": "Links abbiegen auf Kriegsbergstraße"},
                {"distance": 0.0, "duration": 0.0, "instruction": "Ziel erreicht"},
            ]}],
        },
    }],
}


def make_router(fake: FakeNominatim, api_key="test-key", **kwargs) -> OrsClient:
    return OrsClient(
        base_url=kwargs.pop("base_url", "https://ors.test/openrouteservice"),
        api_key=api_key,
        rate_limiter=kwargs.pop("rate_limiter", RateLimiter(0)),
        transport=httpx.MockTransport(fake),
        **kwargs,
    )


def encode_polyline(coords, precision=6):
    """Test helper: [[lat, lon], ...] -> Google encoded polyline."""
    out, prev = [], [0, 0]
    for lat, lon in coords:
        for i, v in enumerate((lat, lon)):
            n = round(v * 10 ** precision)
            d, prev[i] = n - prev[i], n
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
    return "".join(out)


def _place(name, lat, lon, track=None):
    p = {"name": name, "lat": lat, "lon": lon}
    if track:
        p["track"] = track
    return p


def _walk(a, b, minutes, start="2026-11-17T08:00:00Z"):
    return {"mode": "WALK", "from": a, "to": b, "duration": minutes * 60, "distance": minutes * 80,
            "startTime": start, "endTime": start,
            "legGeometry": {"points": encode_polyline([[a["lat"], a["lon"]], [b["lat"], b["lon"]]]),
                            "precision": 6, "length": 2}}


def _ride(mode, line, headsign, a, b, minutes, start, color="58102f", wheelchair="NOT_ACCESSIBLE"):
    return {"mode": mode, "displayName": line, "routeShortName": line, "headsign": headsign,
            "from": a, "to": b, "duration": minutes * 60, "startTime": start, "endTime": start,
            "routeColor": color, "wheelchairAccessible": wheelchair,
            "legGeometry": {"points": encode_polyline([[a["lat"], a["lon"]], [b["lat"], b["lon"]]]),
                            "precision": 6, "length": 2}}


START_P = _place("START", 48.770, 9.180)
END_P = _place("END", 48.784, 9.171)
STOP_A = _place("Hegelstraße", 48.772, 9.178)
STOP_B = _place("Freibad", 48.775, 9.176)
STOP_C = _place("Uni-Kliniken Berg", 48.783, 9.172, track="1")
STOP_D = _place("Hauptbahnhof", 48.776, 9.180, track="B")


def _itin(minutes_start, legs_spec):
    legs, total, transfers = [], 0, -1
    for kind, *args in legs_spec:
        if kind == "walk":
            legs.append(_walk(*args))
            total += args[2]
        else:
            mode, line, headsign, a, b, mins = args
            legs.append(_ride(mode, line, headsign, a, b, mins,
                              f"2026-11-17T{8 + minutes_start // 60:02d}:{minutes_start % 60:02d}:00Z"))
            total += mins
            transfers += 1
    return {"duration": total * 60, "startTime": "2026-11-17T08:00:00Z",
            "endTime": "2026-11-17T09:00:00Z", "transfers": transfers, "id": "x", "legs": legs}


def make_transit_sample():
    its = []
    for m in (0, 30, 60, 90):      # Bus 5, every 30 min, 31 min total
        its.append(_itin(m + 11, [("walk", START_P, STOP_A, 11),
                                  ("ride", "BUS", "5", "Ahornweg", STOP_A, STOP_C, 16),
                                  ("walk", STOP_C, END_P, 4)]))
    for m in (7, 37, 67, 97):      # Bus 19, every 30 min, 28 min total -> best
        its.append(_itin(m + 8, [("walk", START_P, STOP_B, 8),
                                 ("ride", "BUS", "19", "BG Unfallklinik", STOP_B, STOP_C, 16),
                                 ("walk", STOP_C, END_P, 4)]))
    its.append(_itin(21, [("walk", START_P, STOP_A, 11),          # one transfer, once
                          ("ride", "BUS", "8", "Käppele", STOP_A, STOP_D, 5),
                          ("ride", "BUS", "13", "BG Unfallklinik", STOP_D, STOP_C, 12),
                          ("walk", STOP_C, END_P, 4)]))
    # deep copy: no shared place objects between tests
    return copy.deepcopy({"from": START_P, "to": END_P, "direct": [], "itineraries": its})


def make_transit(fake, has_contact=True, **kwargs) -> TransitousClient:
    return TransitousClient(
        base_url="https://transit.test",
        user_agent="Wegweiser/test (test@example.org)",
        has_contact=has_contact,
        rate_limiter=kwargs.pop("rate_limiter", RateLimiter(0)),
        transport=httpx.MockTransport(fake),
        **kwargs,
    )


@pytest.fixture
def fake_transit():
    return FakeNominatim(json_body=make_transit_sample())


@pytest.fixture
def fake_ors():
    return FakeNominatim(json_body=SAMPLE_ROUTE)


@pytest.fixture
def fake_nominatim():
    return FakeNominatim()


@pytest.fixture
def client(tmp_path, monkeypatch, fake_nominatim, fake_ors, fake_transit):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite"))
    from app import auth
    monkeypatch.setattr(auth, "_N", 2 ** 8)   # fast password hashing in tests
    from app.main import app

    app.dependency_overrides[get_geocoder] = lambda: make_client(fake_nominatim)
    app.dependency_overrides[get_router] = lambda: make_router(fake_ors)
    app.dependency_overrides[get_transit] = lambda: make_transit(fake_transit)
    with TestClient(app) as c:
        # Logged in as admin: most tests exercise editing; anon_client is a browser without login
        from app import auth, db
        with db.get_conn() as conn:
            db.create_admin(conn, ADMIN_USER, auth.hash_password(ADMIN_PASSWORD))
        r = c.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
                   follow_redirects=False)
        assert r.status_code == 303, r.text
        yield c
    app.dependency_overrides.clear()


ADMIN_USER = "admin"
ADMIN_PASSWORD = "correct horse battery"


@pytest.fixture
def anon_client(client):
    """Another browser on the same instance, not logged in (own cookies)."""
    from app.main import app
    return TestClient(app)
