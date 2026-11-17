def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_redirects_to_directions(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/directions"


def test_empty_list(client):
    r = client.get("/locations")
    assert r.status_code == 200
    assert "Noch keine Standorte" in r.text


def _create(client, **overrides):
    data = {"name": "Wohngruppe Nord", "address": "Hauptstr. 1, 70173 Stuttgart",
            "lat": "48.7758", "lon": "9.1829"} | overrides
    return client.post("/locations", data=data, follow_redirects=False)


def test_create_and_list(client):
    r = _create(client)
    assert r.status_code == 303
    page = client.get("/locations").text
    assert "Wohngruppe Nord" in page
    assert "48.775800, 9.182900" in page


def test_create_accepts_decimal_comma(client):
    assert _create(client, lat="48,5", lon="9,25").status_code == 303
    assert "48.500000, 9.250000" in client.get("/locations").text


def test_create_validation(client):
    r = _create(client, name="  ", lat="abc", lon="200")
    assert r.status_code == 422
    assert "Name darf nicht leer sein." in r.text
    assert "Breitengrad ist keine gültige Zahl." in r.text
    assert "Längengrad muss zwischen" in r.text
    assert "Noch keine Standorte" in r.text


def test_edit_and_update(client):
    _create(client)
    r = client.get("/locations/1/edit")
    assert r.status_code == 200
    assert "Standort bearbeiten" in r.text
    r = client.post("/locations/1", data={"name": "Wohngruppe Süd", "address": "Neue Str. 2",
                                          "lat": "48.1", "lon": "9.1"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/locations").text
    assert "Wohngruppe Süd" in page
    assert "Wohngruppe Nord" not in page


def test_delete(client):
    _create(client)
    r = client.post("/locations/1/delete", follow_redirects=False)
    assert r.status_code == 303
    assert "Noch keine Standorte" in client.get("/locations").text


def test_missing_location_404(client):
    assert client.get("/locations/99/edit").status_code == 404
    assert client.post("/locations/99/delete").status_code == 404


def test_name_is_html_escaped(client):
    _create(client, name="O'Brien <b>x</b>")
    page = client.get("/locations").text
    assert "<b>x</b>" not in page
    assert "O&#39;Brien &lt;b&gt;x&lt;/b&gt;" in page
