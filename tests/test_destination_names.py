"""Translated destination names and category names in the directions language."""

from app.category_names import KEYS, NAMES, category_name
from app.i18n import DIRECTIONS_LANGUAGES
from app.services.geocoding import parse_result, translated_names
from tests.conftest import SAMPLE_RESULT

LOC = {"name": "EA", "address": "a, 72072 Tübingen", "lat": "48.5", "lon": "9.0"}
DEST = {"name": "Kinderklinik", "address": "x", "lat": "48.53", "lon": "9.04", "phone": "",
        "website": "", "opening_hours": "", "google_maps_url": "", "note": "", "osm_type": "",
        "osm_id": "", "category": "hospital"}


def test_every_directions_language_has_all_category_names():
    for lang in DIRECTIONS_LANGUAGES:
        assert set(NAMES[lang]) == set(KEYS), lang
        assert all(NAMES[lang].values()), lang
    assert category_name("optician", "tr") == "Gözlükçü"
    assert category_name("other", "en") == "" and category_name("", "en") == ""


def test_translated_names_from_osm_namedetails():
    details = {"name": "Kinderklinik", "name:en": "Children's hospital", "name:el": "Παιδιατρική",
               "name:uk": "Дитяча лікарня", "name:fr": "Kinderklinik", "name:xx": "?"}
    assert translated_names(details, "Kinderklinik") == {
        "en": "Children's hospital", "gr": "Παιδιατρική", "ua": "Дитяча лікарня"}
    assert parse_result(SAMPLE_RESULT).names == translated_names(
        SAMPLE_RESULT.get("namedetails") or {}, parse_result(SAMPLE_RESULT).name)


def _page(client, lang):
    return client.get("/directions/print", params={"location_id": 1, "destination_id": 1,
                                                   "lang": lang, "profile": "foot-walking"}).text


def test_names_saved_and_shown_as_subtitle(client, fake_ors):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST | {"name_en": " Children's hospital ", "name_ar": ""})
    edit = client.get("/destinations/1/edit").text
    assert 'name="name_en" value="Children&#39;s hospital"' in edit
    assert 'name="name_ar" value=""' in edit and 'dir="rtl"' in edit
    # translated name for English, kind of place otherwise
    assert '<p class="dest-subtitle">Children&#39;s hospital</p>' in _page(client, "en")
    assert '<p class="dest-subtitle">Hastane</p>' in _page(client, "tr")
    assert '<p class="dest-subtitle">Krankenhaus</p>' in _page(client, "de")
    # removing the translation falls back to the category
    client.post("/destinations/1", data=DEST | {"name_en": ""})
    assert '<p class="dest-subtitle">Hospital</p>' in _page(client, "en")


def test_no_subtitle_without_category(client, fake_ors):
    client.post("/locations", data=LOC)
    client.post("/destinations", data=DEST | {"category": ""})
    assert "dest-subtitle" not in _page(client, "en")


def test_review_page_lists_category_names(client):
    page = client.get("/translations", params={"lang": "ar"}).text
    assert "<h2>Kategorien</h2>" in page and "مستشفى" in page
