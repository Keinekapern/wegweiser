import httpx
import pytest

from app import db
from app.services.ratelimit import RateLimiter
from app.services.geocoding import (GeocodingError, format_address,
                                    parse_result)
from tests.conftest import SAMPLE_RESULT, FakeNominatim, make_client


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "geo.sqlite")
    db.migrate(c)
    yield c
    c.close()


def test_parse_result_maps_osm_tags():
    c = parse_result(SAMPLE_RESULT)
    assert c.name == "Katharinenhospital"
    assert c.address == "Kriegsbergstraße 60, 70174 Stuttgart"
    assert (c.lat, c.lon) == (48.784, 9.171)
    assert c.phone == "+49 711 27801"
    assert c.website == "https://www.klinikum-stuttgart.de"
    assert c.opening_hours == "24/7"
    assert (c.osm_type, c.osm_id) == ("way", 4711)


def test_parse_result_contact_tags_and_fallbacks():
    item = {"lat": "1", "lon": "2", "osm_type": "node", "osm_id": 5, "name": "",
            "display_name": "Irgendwo, Deutschland",
            "address": {}, "extratags": {"contact:phone": "0711 1", "contact:website": "x.de"}}
    c = parse_result(item)
    assert c.address == "Irgendwo, Deutschland"
    assert c.name == "Irgendwo, Deutschland"
    assert c.phone == "0711 1"
    assert c.website == "x.de"


def test_format_address_town():
    assert format_address({"road": "Markt", "postcode": "72070", "town": "Tübingen"}) == \
        "Markt, 72070 Tübingen"


def test_search_sends_policy_compliant_request(conn):
    fake = FakeNominatim()
    results, cached = make_client(fake).search(conn, "Katharinenhospital")
    assert not cached and len(results) == 1
    req = fake.requests[0]
    assert req.url.path == "/search"
    assert req.headers["User-Agent"] == "Wegweiser/test"
    params = req.url.params
    assert params["format"] == "jsonv2"
    assert params["extratags"] == "1"
    assert params["countrycodes"] == "de"
    assert params["q"] == "Katharinenhospital"


def test_search_uses_cache(conn):
    fake = FakeNominatim()
    client = make_client(fake)
    client.search(conn, "Katharinenhospital")
    results, cached = client.search(conn, "  katharinenHOSPITAL ")
    assert cached
    assert results[0].name == "Katharinenhospital"
    assert len(fake.requests) == 1


def test_empty_results_are_cached(conn):
    fake = FakeNominatim(json_body=[])
    client = make_client(fake)
    assert client.search(conn, "gibtsnicht") == ([], False)
    assert client.search(conn, "gibtsnicht") == ([], True)
    assert len(fake.requests) == 1


def test_expired_cache_is_refreshed(conn):
    fake = FakeNominatim()
    client = make_client(fake)
    client.search(conn, "Katharinenhospital")
    with conn:
        conn.execute("UPDATE api_cache SET fetched_at = datetime('now', '-31 days')")
    _, cached = client.search(conn, "Katharinenhospital")
    assert not cached
    assert len(fake.requests) == 2


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_errors_raise_and_are_not_cached(conn, status):
    fake = FakeNominatim(status=status)
    client = make_client(fake)
    with pytest.raises(GeocodingError):
        client.search(conn, "Katharinenhospital")
    assert conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0] == 0


def test_network_error_raises(conn):
    def boom(request):
        raise httpx.ConnectError("down")
    client = make_client(FakeNominatim())
    client._http = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(GeocodingError):
        client.search(conn, "Katharinenhospital")


def test_rate_limiter_spaces_calls():
    now = [100.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(1.0, clock=lambda: now[0], sleep=sleep)
    limiter.wait()
    limiter.wait()
    now[0] += 0.3
    limiter.wait()
    assert slept == [pytest.approx(1.0), pytest.approx(0.7)]


def test_rate_limiter_applies_to_uncached_requests_only(conn):
    calls = []

    class CountingLimiter(RateLimiter):
        def wait(self):
            calls.append(1)

    client = make_client(FakeNominatim(), rate_limiter=CountingLimiter(1.0))
    client.search(conn, "Katharinenhospital")
    client.search(conn, "Katharinenhospital")
    assert len(calls) == 1
