"""Export and import of destinations and locations."""

import csv
import io
import json
import re

from app import db

BASE = {"phone": "", "website": "", "opening_hours": "", "google_maps_url": "", "note": "",
        "osm_type": "", "osm_id": "", "category": ""}


def _setup(client):
    client.post("/locations", data={"name": "EA Tübingen", "address": "Beispielweg 1", "coords": "48.5, 9.0"})
    client.post("/locations", data={"name": "NUK", "address": "Musterstraße 2", "coords": "48.7, 9.0"})
    client.post("/destinations", data=BASE | {
        "name": "Kinderklinik", "address": "Hoppe-Seyler-Str. 1, 72076 Tübingen",
        "coords": "48.53, 9.04", "phone": "07071 29-83781", "category": "hospital",
        "osm_type": "way", "osm_id": "123", "name_en": "Children's hospital", "name_ar": "مستشفى الأطفال",
        "location_ids": ["1"]})
    client.post("/destinations", data=BASE | {"name": "Apotheke", "address": "Markt 1, 72070 Tübingen",
                                              "coords": "48.52, 9.05", "category": "pharmacy"})


def _token(html: str) -> str:
    return re.search(r'action="/settings/data/import/([^"]+)"', html).group(1)


def _upload(client, name, content: bytes):
    return client.post("/settings/data/import", files={"file": (name, content)})


def test_json_export_without_and_with_locations(client):
    _setup(client)
    data = client.get("/settings/data/export", params={"format": "json"}).json()
    assert data["format"] == "wegweiser-data" and "locations" not in data
    kinder = next(d for d in data["destinations"] if d["name"] == "Kinderklinik")
    assert kinder["names"] == {"en": "Children's hospital", "ar": "مستشفى الأطفال"}
    assert "locations" not in kinder and kinder["phone"] == "+49 7071 29-83781"
    r = client.get("/settings/data/export", params={"format": "json", "locations": "1"})
    assert "filename*=UTF-8''Wegweiser_Daten_" in r.headers["content-disposition"]
    data = r.json()
    assert [l["name"] for l in data["locations"]] == ["EA Tübingen", "NUK"]
    assert next(d for d in data["destinations"] if d["name"] == "Kinderklinik")["locations"] == ["EA Tübingen"]


def test_pending_destinations_only_on_request(client, anon_client):
    anon_client.post("/destinations", data=BASE | {"name": "Neu", "address": "x", "coords": "48.5, 9.0"})
    assert client.get("/settings/data/export").json()["destinations"] == []
    assert len(client.get("/settings/data/export", params={"pending": "1"}).json()["destinations"]) == 1


def test_csv_export_for_excel(client):
    _setup(client)
    text = client.get("/settings/data/export", params={"format": "csv"}).content.decode("utf-8")
    assert text.startswith("﻿Name;Adresse;Koordinaten;")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    header, kinder = rows[0], next(r for r in rows if r[0] == "Kinderklinik")
    assert "Standorte" not in header and "Name (en)" in header
    assert kinder[2] == "48.53, 9.04" and kinder[header.index("Kategorie")] == "Krankenhaus"
    assert kinder[header.index("Name (en)")] == "Children's hospital"
    with_locs = client.get("/settings/data/export", params={"format": "csv", "locations": "1"}).text
    assert ";Standorte;" in with_locs.splitlines()[0]
    locs = client.get("/settings/data/export", params={"format": "csv-locations"}).text
    assert locs.splitlines()[1] == "EA Tübingen;Beispielweg 1;48.5, 9.0"


def test_roundtrip_into_an_empty_instance(client, tmp_path, monkeypatch):
    _setup(client)
    exported = client.get("/settings/data/export", params={"format": "json", "locations": "1"}).content
    with db.get_conn() as conn:                       # empty the instance
        conn.execute("DELETE FROM destinations")
        conn.execute("DELETE FROM locations")
        conn.commit()
    preview = _upload(client, "w.json", exported).text
    assert "Neu: 2 – werden angelegt" in preview and "Neu: 2 – werden angelegt" in preview
    done = client.post(f"/settings/data/import/{_token(preview)}").text
    assert "Import abgeschlossen: 4 neu, 0 aktualisiert, 0 übersprungen." in done
    with db.get_conn() as conn:
        kinder = next(d for d in db.list_destinations(conn) if d.name == "Kinderklinik")
        assert kinder.category == "hospital" and kinder.osm_id == 123 and kinder.status == "approved"
        assert db.get_destination_names(conn, kinder.id)["ar"] == "مستشفى الأطفال"
        locs = {l.id: l.name for l in db.list_locations(conn)}
        assert [locs[i] for i in db.destination_location_ids(conn)[kinder.id]] == ["EA Tübingen"]


def test_duplicates_preview_and_update_choice(client):
    _setup(client)
    data = client.get("/settings/data/export", params={"format": "json"}).json()
    same = _upload(client, "w.json", json.dumps(data).encode()).text
    assert "Schon vorhanden und gleich: 2" in same and "Neu:" not in same
    for d in data["destinations"]:
        if d["name"] == "Kinderklinik":
            d["phone"] = "+49 7071 1234"
            d["name"] = "Kinderklinik"            # matched by OSM object
        else:
            d["note"] = "Notdienst am Wochenende"
    preview = _upload(client, "w.json", json.dumps(data).encode()).text
    assert "Schon vorhanden, aber abweichend: 2" in preview
    assert "+49 7071 29-83781</span> → +49 7071 1234" in preview
    # update only the Kinderklinik (line 1 in the file)
    line = next(i for i, d in enumerate(data["destinations"], 1) if d["name"] == "Kinderklinik")
    done = client.post(f"/settings/data/import/{_token(preview)}",
                       data={"update": [f"destination:{line}"]}).text
    assert "0 neu, 1 aktualisiert, 1 übersprungen" in done
    with db.get_conn() as conn:
        by_name = {d.name: d for d in db.list_destinations(conn)}
        assert by_name["Kinderklinik"].phone == "+49 7071 1234"
        assert by_name["Apotheke"].note == ""
        # names and assignments not in the file stay as they were
        assert db.get_destination_names(conn, by_name["Kinderklinik"].id)["en"] == "Children's hospital"
        assert db.destination_location_ids(conn)[by_name["Kinderklinik"].id] == [1]


def test_csv_import_english_headers_excel_encoding(client):
    _setup(client)
    text = ("Name,Address,Coordinates,Phone,Category,Locations,Name (fa)\r\n"
            "Zahnarzt Müller,\"Weg 3, 72070 Tübingen\",\"48.51, 9.06\",07071 555,Zahnarzt,EA Tübingen | Sindelfingen,دندانپزشک\r\n"
            "Kaputt,Weg 4,abc,,,,\r\n")
    preview = _upload(client, "liste.csv", text.encode("utf-8")).text
    assert "Neu: 1" in preview and "Fehlerhaft: 1" in preview
    assert "Diese Standorte aus der Datei gibt es hier nicht" in preview and "Sindelfingen" in preview
    client.post(f"/settings/data/import/{_token(preview)}")
    with db.get_conn() as conn:
        z = next(d for d in db.list_destinations(conn) if d.name == "Zahnarzt Müller")
        assert z.category == "dentist" and z.phone == "+49 7071 555"
        assert db.get_destination_names(conn, z.id) == {"fa": "دندانپزشک"}
        assert db.destination_location_ids(conn)[z.id] == [1]
    # Excel on Windows saves "CSV" as cp1252
    latin = "Name;Adresse;Koordinaten\r\nBüro Süd;Straße 5;48.4, 9.1\r\n".encode("cp1252")
    preview = _upload(client, "standorte.csv", latin).text
    assert "Büro Süd" in preview and "Standorte" in preview


def test_bad_files(client):
    assert "keine Export-Datei von Wegweiser" in _upload(client, "x.json", b'{"a": 1}').text
    assert "kein gültiges JSON" in _upload(client, "x.json", b"{nope").text
    assert "mindestens die Spalten" in _upload(client, "x.csv", b"Foo;Bar\r\n1;2\r\n").text
    assert "leer" in _upload(client, "x.csv", b"").text
    r = client.post("/settings/data/import/unknown-token")
    assert r.status_code == 410 and "abgelaufen" in r.text


def test_admins_only(client, anon_client):
    for url in ("/settings/data", "/settings/data/export"):
        assert anon_client.get(url, follow_redirects=False).headers["location"].startswith("/admin/login")
    assert "/settings/data" in client.get("/admin").text
