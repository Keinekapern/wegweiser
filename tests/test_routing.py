import json

import httpx
import pytest

from app import db
from app.services.routing import RoutingError, parse_route
from tests.conftest import SAMPLE_ROUTE, FakeNominatim, make_router

START = (48.77, 9.18)
END = (48.784, 9.171)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "route.sqlite")
    db.migrate(c)
    yield c
    c.close()


def test_parse_route():
    r = parse_route("driving-car", SAMPLE_ROUTE)
    assert r.geometry[0] == [48.77, 9.18]  # lat, lon for Leaflet
    assert (r.distance_m, r.duration_s) == (1834.2, 312.5)
    assert [s.instruction for s in r.steps][1] == "Links abbiegen auf Kriegsbergstraße"


def test_request_format(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    make_router(fake).route(conn, "foot-walking", START, END)
    req = fake.requests[0]
    assert req.method == "POST"
    assert str(req.url) == "https://ors.test/openrouteservice/v2/directions/foot-walking/geojson"
    assert req.headers["Authorization"] == "test-key"
    body = json.loads(req.content)
    assert body["coordinates"] == [[9.18, 48.77], [9.171, 48.784]]  # lon, lat
    assert body["language"] == "de"


def test_language_is_sent_and_part_of_cache_key(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    router = make_router(fake)
    router.route(conn, "driving-car", START, END, language="tr")
    router.route(conn, "driving-car", START, END, language="tr")
    router.route(conn, "driving-car", START, END, language="en")
    assert [json.loads(r.content)["language"] for r in fake.requests] == ["tr", "en"]


def test_unknown_language_falls_back_to_german(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    make_router(fake).route(conn, "driving-car", START, END, language="xx")
    assert json.loads(fake.requests[0].content)["language"] == "de"


def test_route_is_cached_and_counted(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    router = make_router(fake)
    assert router.route(conn, "driving-car", START, END)[1] is False
    assert router.route(conn, "driving-car", START, END)[1] is True
    assert router.route(conn, "foot-walking", START, END)[1] is False
    assert len(fake.requests) == 2
    assert db.usage_today(conn, "ors-directions") == 2


def test_daily_limit_blocks_requests(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    router = make_router(fake, daily_limit=1)
    router.route(conn, "driving-car", START, END)
    with pytest.raises(RoutingError, match="Tageslimit"):
        router.route(conn, "foot-walking", START, END)
    assert len(fake.requests) == 1


def test_missing_api_key(conn):
    fake = FakeNominatim(json_body=SAMPLE_ROUTE)
    with pytest.raises(RoutingError, match="ORS_API_KEY"):
        make_router(fake, api_key="").route(conn, "driving-car", START, END)
    assert fake.requests == []


def test_unknown_profile(conn):
    with pytest.raises(RoutingError):
        make_router(FakeNominatim()).route(conn, "cycling-road", START, END)


@pytest.mark.parametrize("status,body,match", [
    (403, {"error": "Access to this API has been disallowed"}, "abgelehnt"),
    (429, {"error": "Rate limit exceeded"}, "Zu viele"),
    (404, {"error": {"code": 2010, "message": "Could not find routable point"}}, "Code 2010"),
])
def test_http_errors(conn, status, body, match):
    router = make_router(FakeNominatim(status=status, json_body=body))
    with pytest.raises(RoutingError, match=match):
        router.route(conn, "driving-car", START, END)
    assert conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0] == 0


def test_network_error(conn):
    router = make_router(FakeNominatim())
    router._http = httpx.Client(transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    with pytest.raises(RoutingError, match="nicht erreichbar"):
        router.route(conn, "driving-car", START, END)


def test_malformed_response(conn):
    router = make_router(FakeNominatim(json_body={"features": []}))
    with pytest.raises(RoutingError, match="unerwartet"):
        router.route(conn, "driving-car", START, END)


def test_generated_language_requests_english_and_keeps_maneuver_data(conn):
    data = json.loads(json.dumps(SAMPLE_ROUTE))
    data["features"][0]["properties"]["segments"][0]["steps"][1].update(
        {"type": 0, "name": "Kriegsbergstraße"})
    fake = FakeNominatim(json_body=data)
    route, _ = make_router(fake).route(conn, "driving-car", START, END, language="ti")
    assert json.loads(fake.requests[0].content)["language"] == "en"
    assert route.steps[1].type == 0 and route.steps[1].name == "Kriegsbergstraße"
    # same cache entry for all generated languages
    make_router(fake).route(conn, "driving-car", START, END, language="ar")
    assert len(fake.requests) == 1
