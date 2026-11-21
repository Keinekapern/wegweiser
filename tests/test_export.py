"""Server-side PDFs and the bulk export (renderer faked: no browser, no tile requests)."""

import io
import zipfile
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import db, export_names
from app.services import export, pdf


class FakeRenderer:
    def __init__(self, fail_dest=None, busy=False):
        self.fail_dest = fail_dest
        self.busy = busy
        self.urls = []

    def __enter__(self):
        if self.busy:
            raise pdf.RendererBusy("busy")
        return self

    def __exit__(self, *exc):
        pass

    def render(self, url):
        self.urls.append(url)
        q = parse_qs(urlsplit(url).query)
        if self.fail_dest and q["destination_id"] == [str(self.fail_dest)]:
            return b"", "errors", "Keine ÖPNV-Verbindung gefunden."
        return b"%PDF-fake " + url.encode(), "ok", None

    def render_html(self, html):
        self.overview = html
        return b"%PDF-overview"


@pytest.fixture
def fake(monkeypatch):
    renderer = FakeRenderer()
    monkeypatch.setattr(pdf, "open_renderer", lambda lock_timeout=None: renderer)

    class Inline:                          # run export jobs synchronously
        def submit(self, fn, *args):
            fn(*args)
    monkeypatch.setattr(export, "_executor", Inline())
    monkeypatch.setattr(export, "_jobs", {})
    return renderer


def _setup(client):
    client.post("/locations", data={"name": "EA Tübingen", "address": "x", "coords": "48.52, 9.05"})
    client.post("/locations", data={"name": "NUK Sindelfingen", "address": "y", "coords": "48.7, 9.0"})
    base = {"address": "Weg 1", "phone": "", "website": "", "opening_hours": "",
            "google_maps_url": "", "note": "", "osm_type": "", "osm_id": "", "category": ""}
    client.post("/destinations", data=base | {"name": "CRONA-Kliniken", "lat": "48.53", "lon": "9.04",
                                               "location_ids": ["1"]})
    client.post("/destinations", data=base | {"name": "Kliniken Böblingen", "lat": "48.68", "lon": "9.0",
                                               "location_ids": ["2"]})
    client.post("/destinations", data=base | {"name": "Apotheke: am Markt?", "lat": "48.6", "lon": "9.0"})


# --- names ---

def test_safe_names():
    assert export_names.safe('Praxis Dr. A/B: "Kinder"?') == "Praxis Dr. A-B- -Kinder--"
    assert export_names.safe("Zentrum.  ") == "Zentrum"
    assert export_names.safe("  ") == "Ohne Namen"
    long = export_names.safe("Universitätsklinik für Zahn-, Mund- und Kieferheilkunde " * 3)
    assert len(long) <= export_names.MAX_PART and not long.endswith(" ")


def test_destination_folders_unique():
    d = lambda i, name, addr: db.Destination(id=i, name=name, address=addr, lat=0, lon=0)
    names = export_names.destination_folders([
        d(1, "Apotheke am Markt", "Hauptstraße 3, 72070 Tübingen"),
        d(2, "Apotheke am Markt", "Marktplatz 1, 71032 Böblingen"),
        d(3, "Apotheke am Markt", "Marktplatz 1, 71032 Böblingen"),
        d(4, "Kinderklinik", "x")])
    assert names == {1: "Apotheke am Markt (Hauptstraße 3)", 2: "Apotheke am Markt (Marktplatz 1) 2",
                     3: "Apotheke am Markt (Marktplatz 1) 3", 4: "Kinderklinik"}


def test_file_and_zip_names():
    assert export_names.pdf_name("CRONA-Kliniken", "ar") == "CRONA-Kliniken – Arabisch.pdf"
    assert export_names.pdf_name("CRONA-Kliniken", "fa", "transit") == \
        "CRONA-Kliniken – Persisch (Farsi) – ÖPNV.pdf"
    loc = lambda i, n: db.Location(i, n, "", 0, 0)
    day = date(2026, 11, 21)
    assert export_names.zip_name([loc(1, "EA Tübingen")], day) == "Wegweiser_2026-11-21_EA-Tübingen.zip"
    assert export_names.zip_name([loc(1, "A"), loc(2, "B"), loc(3, "C")], day) == \
        "Wegweiser_2026-11-21_3-Standorte.zip"


# --- plan ---

def test_plan_one_location(client):
    _setup(client)
    with db.get_conn() as conn:
        items, name = export.plan(conn, export.ExportRequest([1], [1, 2, 3], ["de", "ar"], ["transit"]))
    # Kliniken Böblingen is only offered at Sindelfingen; unassigned destinations everywhere
    assert [it.path for it in items] == [
        "Apotheke- am Markt-/Apotheke- am Markt- – Arabisch.pdf",
        "Apotheke- am Markt-/Apotheke- am Markt- – Deutsch.pdf",
        "CRONA-Kliniken/CRONA-Kliniken – Arabisch.pdf",
        "CRONA-Kliniken/CRONA-Kliniken – Deutsch.pdf"]
    assert name.endswith("_EA-Tübingen.zip")
    q = parse_qs(urlsplit(items[2].print_url(export.ExportRequest([1], [1], ["ar"], ["transit"],
                                                                  "landscape", True))).query)
    assert q == {"location_id": ["1"], "destination_id": ["1"], "profile": ["transit"],
                 "lang": ["ar"], "orientation": ["landscape"], "bw": ["1"]}


def test_plan_several_locations_and_modes(client):
    _setup(client)
    with db.get_conn() as conn:
        items, name = export.plan(conn, export.ExportRequest([1, 2], [1, 2], ["de"],
                                                             ["transit", "foot-walking"]))
    assert [it.path for it in items] == [
        "EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Deutsch – ÖPNV.pdf",
        "EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Deutsch – zu Fuß.pdf",
        "NUK Sindelfingen/Kliniken Böblingen/Kliniken Böblingen – Deutsch – ÖPNV.pdf",
        "NUK Sindelfingen/Kliniken Böblingen/Kliniken Böblingen – Deutsch – zu Fuß.pdf"]
    assert name.endswith("_2-Standorte.zip")


# --- bulk export via the UI ---

def test_bulk_export_zip(client, fake):
    _setup(client)
    fake.fail_dest = 2
    page = client.get("/export").text
    assert "Export starten" in page and "CRONA-Kliniken" in page
    r = client.post("/export", data={"location_ids": ["1", "2"], "destination_ids": ["1", "2"],
                                     "langs": ["de", "ar"], "modes": ["auto"],
                                     "orientation": "portrait"}, follow_redirects=False)
    assert r.status_code == 303
    job_url = r.headers["location"]
    state = client.get(job_url + "/status").json()
    assert state["status"] == "done" and state["done"] == 4 and state["problems"] == 2
    assert "ZIP herunterladen" in client.get(job_url).text
    dl = client.get(job_url + "/download")
    assert dl.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''Wegweiser_" in dl.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(dl.content)).namelist()
    assert names == ["EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Arabisch.pdf",
                     "EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Deutsch.pdf",
                     "Übersicht.pdf"]
    assert "Keine ÖPNV-Verbindung gefunden." in fake.overview      # listed as not created
    assert "Kliniken Böblingen" in fake.overview and "2 von 4" in fake.overview


def test_bulk_export_validation(client, fake, monkeypatch):
    _setup(client)
    r = client.post("/export", data={"location_ids": ["1"], "destination_ids": ["2"],
                                     "langs": ["de"], "modes": ["auto"]})
    assert r.status_code == 422 and "keine Ziele" in r.text
    r = client.post("/export", data={"location_ids": ["1"]})
    assert "mindestens ein Ziel" in r.text and "mindestens eine Sprache" in r.text
    monkeypatch.setattr(export, "MAX_FILES", 1)
    r = client.post("/export", data={"location_ids": ["1"], "destination_ids": ["1"],
                                     "langs": ["de", "en"], "modes": ["auto"]})
    assert "Das wären 2 PDFs" in r.text


def test_bulk_export_admins_only(client, anon_client, fake):
    _setup(client)
    assert anon_client.get("/export", follow_redirects=False).headers["location"].startswith("/admin/login")
    assert anon_client.post("/export", data={}, follow_redirects=False).status_code == 303
    assert ">Export<" not in anon_client.get("/directions").text
    assert ">Export<" in client.get("/directions").text


# --- single PDF ---

def test_single_pdf(client, anon_client, fake):
    _setup(client)
    r = anon_client.get("/directions/pdf", params={"location_id": 1, "destination_id": 1,
                                                   "profile": "transit", "lang": "ar", "bw": "1"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''CRONA-Kliniken%20%E2%80%93%20Arabisch.pdf" in r.headers["content-disposition"]
    assert fake.urls[-1].startswith("/directions/print?") and "bw=1" in fake.urls[-1]
    assert "pdf-button" in anon_client.get("/directions/print", params={"location_id": 1,
                                                                        "destination_id": 1}).text
    assert anon_client.get("/directions/pdf", params={"location_id": 1, "destination_id": 99}).status_code == 404


def test_single_pdf_while_export_runs(client, fake):
    _setup(client)
    fake.busy = True
    r = client.get("/directions/pdf", params={"location_id": 1, "destination_id": 1})
    assert r.status_code == 503 and "PDF-Export" in r.text


# --- tile cache ---

def test_tile_pattern():
    p = pdf.tile_pattern("https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    assert p.match("https://tile.openstreetmap.org/15/17015/11284.png")
    assert not p.match("https://tile.openstreetmap.org.evil/15/1/1.png")
    assert pdf.tile_pattern("https://{s}.tiles.example/{z}/{x}/{y}{r}.png").match(
        "https://b.tiles.example/3/4/5@2x.png")


def test_tile_cache_fetches_once(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "TILE_MIN_INTERVAL_S", 0)
    calls = []

    def handler(request):
        calls.append(request)
        if "404" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=b"\x89PNG tile", headers={"content-type": "image/png"})

    cache = pdf.TileCache(tmp_path, "wegweiser-test", transport=httpx.MockTransport(handler))
    url = "https://tile.openstreetmap.org/15/1/1.png"
    assert cache.get(url) == (b"\x89PNG tile", "image/png")
    assert cache.get(url) == (b"\x89PNG tile", "image/png")
    assert len(calls) == 1 and calls[0].headers["user-agent"] == "wegweiser-test"
    assert cache.get("https://tile.openstreetmap.org/404/1/1.png") is None


def test_names_follow_the_ui_language(client, fake):
    _setup(client)
    with db.get_conn() as conn:
        items, name = export.plan(conn, export.ExportRequest([1, 2], [1, 2], ["de", "fa"],
                                                             ["transit", "foot-walking"], ui_lang="en"))
    assert items[0].path == "EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – German – public transport.pdf"
    assert items[3].path == "EA Tübingen/CRONA-Kliniken/CRONA-Kliniken – Persian (Farsi) – on foot.pdf"
    assert name.endswith("_2-locations.zip")
    assert export_names.overview_name("en") == "Overview.pdf"
    client.cookies.set("ui_lang", "en")
    r = client.get("/directions/pdf", params={"location_id": 1, "destination_id": 1, "lang": "ar"})
    assert "CRONA-Kliniken%20%E2%80%93%20Arabic.pdf" in r.headers["content-disposition"]
    r = client.post("/export", data={"location_ids": ["1"], "destination_ids": ["1"], "langs": ["de"],
                                     "modes": ["auto"]}, follow_redirects=False)
    names = zipfile.ZipFile(io.BytesIO(client.get(r.headers["location"] + "/download").content)).namelist()
    assert names == ["CRONA-Kliniken/CRONA-Kliniken – German.pdf", "Overview.pdf"]
