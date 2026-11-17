from app import config


def test_favicon_and_name(client):
    page = client.get("/locations").text
    assert "<title>Standorte – Wegweiser</title>" in page
    assert 'rel="icon" href="http://testserver/static/favicon.svg" type="image/svg+xml"' in page
    assert 'rel="apple-touch-icon"' in page
    assert 'class="brand-icon">Wegweiser</a>' in page
    assert client.get("/static/favicon.svg").headers["content-type"].startswith("image/svg+xml")
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_user_agent_uses_new_name():
    assert config.user_agent().startswith("Wegweiser/")


def test_static_files_are_revalidated(client):
    response = client.get("/static/stop.svg")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
