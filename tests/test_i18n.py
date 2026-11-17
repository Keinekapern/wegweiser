import re
import string
from datetime import date
from pathlib import Path

import pytest

from app.i18n import (DIRECTIONS_LANGUAGES, DOC_KEYS, DOC_STRINGS, ENGLISH, JS_MSGIDS,
                      LANGUAGE_NAMES,
                      DirectionsText, Msg, translate)
from app.services.routing import PROFILES
from app.services.transit import MODE_GROUP_LABELS, WEEKDAYS

APP = Path(__file__).parent.parent / "app"


def _template_msgids() -> set[str]:
    ids = set()
    for path in (APP / "templates").glob("*.html"):
        text = path.read_text()
        ids |= set(re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', text))
        ids |= set(re.findall(r"\bt\('((?:[^'\\]|\\.)*)'", text))
    return ids


def _python_msgids() -> set[str]:
    ids = set()
    for path in APP.rglob("*.py"):
        text = path.read_text()
        for m in re.finditer(r'Msg\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', text):
            ids.add("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))))
        ids |= set(re.findall(r'translate\(get_ui_lang\(request\), "([^"]+)"\)', text))
        ids |= set(re.findall(r'(?:required_text|parse_coordinate|optional_url)\([^,]+, "([^"]+)"', text))
    return ids


def _js_msgids() -> set[str]:
    return set(re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', (APP / "static/geosearch.js").read_text()))


def test_all_ui_msgids_have_english_translation():
    used = (_template_msgids() | _python_msgids() | _js_msgids() | set(PROFILES.values())
            | set(LANGUAGE_NAMES.values()) | set(MODE_GROUP_LABELS.values()) | set(WEEKDAYS)
            | {"ÖPNV"})
    assert len(used) > 60
    missing = sorted(used - ENGLISH.keys())
    assert not missing, missing


def test_js_msgids_are_exported():
    assert _js_msgids() <= set(JS_MSGIDS)


def test_english_placeholders_match():
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for de, en in ENGLISH.items():
        assert fields(de) == fields(en), de


def test_translate_msg_with_nested_label():
    msg = Msg("{label} darf nicht leer sein.", label=Msg("Adresse"))
    assert translate("de", msg) == "Adresse darf nicht leer sein."
    assert translate("en", msg) == "Address must not be empty."
    assert str(msg) == "Adresse darf nicht leer sein."


def test_doc_strings_complete_and_consistent():
    assert set(DOC_STRINGS) == set(DIRECTIONS_LANGUAGES)
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for lang, strings in DOC_STRINGS.items():
        assert tuple(strings) == DOC_KEYS
        for key in DOC_KEYS:
            assert strings[key].strip(), (lang, key)
            assert fields(strings[key]) == fields(DOC_STRINGS["de"][key]), (lang, key)
        date.today().strftime(strings["date"])


def test_directions_languages_supported_by_ors():
    # openrouteservice v10.1 APIEnums.Languages (short codes)
    ors = {"cs", "da", "de", "en", "eo", "es", "eu", "fi", "fr", "gr", "he", "hu", "id", "it",
           "ja", "lv", "lt", "ne", "nl", "nb", "pl", "pt", "ro", "ru", "tr", "ua", "vi", "zh"}
    from app.i18n import MANEUVERS, ORS_LANGUAGES
    assert ORS_LANGUAGES <= ors
    assert set(MANEUVERS) == {"ar", "fa", "ta", "so", "ti"}
    assert not set(MANEUVERS) & ors
    assert not {"eo", "eu", "lv", "lt", "ne"} & set(DIRECTIONS_LANGUAGES)
    assert set(LANGUAGE_NAMES) == set(DIRECTIONS_LANGUAGES)


@pytest.mark.parametrize("lang,meters,seconds,expected", [
    ("de", 1834, 312, "1,8 km, ca. 5 Min."),
    ("en", 1834, 312, "1.8 km, approx. 5 min"),
    ("de", 434, 4500, "430 m, ca. 1 Std. 15 Min."),
    ("ru", 12345, 60, "12,3 км, около 1 мин"),
    ("zh", 900, 30, "900 米，约1 分钟"),
])
def test_summary_formatting(lang, meters, seconds, expected):
    assert DirectionsText(lang).summary(meters, seconds) == expected


def test_date_formatting():
    d = date(2026, 3, 7)
    assert DirectionsText("de")("created", date=DirectionsText("de").date(d)) == "Erstellt am 07.03.2026"
    assert DirectionsText("ja").date(d) == "2026/03/07"


def test_ui_language_switch(client):
    r = client.get("/ui-language/en", params={"next": "/destinations?x=1"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/destinations?x=1"
    assert "ui_lang=en" in r.headers["set-cookie"]
    page = client.get("/destinations").text
    assert '<html lang="en">' in page
    assert "No destinations yet." in page
    assert 'Searching' in page  # JS strings exported in UI language


def test_ui_language_switch_rejects_unknown_and_open_redirect(client):
    r = client.get("/ui-language/fr", params={"next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert "set-cookie" not in r.headers
    r = client.get("/ui-language/en", params={"next": "https://evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_validation_errors_in_english(client):
    client.cookies.set("ui_lang", "en")
    r = client.post("/locations", data={"name": "", "address": "x", "lat": "x", "lon": "500"})
    assert r.status_code == 422
    assert "Name must not be empty." in r.text
    assert "Latitude is not a valid number." in r.text
    assert "Longitude must be between -180 and 180." in r.text


def test_api_error_in_english(client, fake_nominatim):
    client.cookies.set("ui_lang", "en")
    fake_nominatim.status = 429
    r = client.get("/api/geocode", params={"q": "Katharinenhospital"})
    assert "Nominatim refused the request" in r.json()["error"]


def test_maneuver_templates_complete():
    from app.i18n import MANEUVER_KEYS, MANEUVERS
    for lang, templates in MANEUVERS.items():
        assert tuple(templates) == MANEUVER_KEYS
        assert "{n}" in templates["roundabout"], lang
        assert all(t.strip() for t in templates.values()), lang


class _Step:
    def __init__(self, type, name="", exit_number=None, instruction="ORS text"):
        self.type, self.name, self.exit_number, self.instruction = type, name, exit_number, instruction


def test_generated_instructions():
    ar = DirectionsText("ar")
    assert ar.instruction(_Step(0, "Wilhelmstraße")) == "انعطف يسارًا – Wilhelmstraße"
    assert ar.instruction(_Step(7, "-", exit_number=2)) == "في الدوار، اسلك المخرج رقم 2"
    assert ar.instruction(_Step(10, "Hoppe-Seyler-Straße")) == "لقد وصلت إلى وجهتك"
    assert DirectionsText("so").instruction(_Step(99)) == "Toos u soco"   # unknown type
    # ORS languages keep the ORS text
    assert DirectionsText("de").instruction(_Step(0, "X")) == "ORS text"


def test_new_languages_rtl_and_units():
    assert DirectionsText("ar").dir == "rtl" and DirectionsText("fa").dir == "rtl"
    assert DirectionsText("ti").dir == "ltr"
    assert DirectionsText("fa").distance(2500) == "2.5 کیلومتر"
    assert DirectionsText("ta").summary(1834, 312) == "1.8 km, சுமார் 5 நிமி."


def test_translations_page(client):
    page = client.get("/translations", params={"lang": "ti"}).text
    assert "ብመኪና" in page and "Mit dem Auto" in page and "By car" in page
    assert "Abbiegehinweise (selbst erzeugt)" in page and "ናብ ጸጋም ተጠወ" in page
    page = client.get("/translations", params={"lang": "tr"}).text
    assert "Arabayla" in page and "selbst erzeugt" not in page
    assert 'dir="rtl"' in client.get("/translations", params={"lang": "ar"}).text


def test_language_options_sorted_by_ui_name():
    from app.i18n import directions_language_options
    de = list(directions_language_options("de"))
    assert de[:2] == ["de", "en"]
    assert de[2:6] == ["ar", "zh", "da", "fi"]          # Arabisch, Chinesisch, Dänisch, Finnisch
    assert de.index("tr") < de.index("ua") < de.index("hu")   # Türkisch < Ukrainisch < Ungarisch
    en = list(directions_language_options("en"))
    assert en[:2] == ["de", "en"]
    assert en[2:5] == ["ar", "zh", "cs"]                 # Arabic, Chinese, Czech
    assert sorted(de) == sorted(en)


def test_dropdown_order_on_page(client):
    client.post("/locations", data={"name": "A", "address": "a", "coords": "48.5, 9.0"})
    client.post("/destinations", data={"name": "Z", "address": "b", "coords": "48.6, 9.1"})
    page = client.get("/directions").text
    pos = [page.index(f'<option value="{c}"') for c in ("de", "en", "ar", "zh", "da")]
    assert pos == sorted(pos)


def test_markup_escapes_text_but_keeps_markup_params():
    from markupsafe import Markup

    from app.deps import stop_name
    from app.i18n import DirectionsText

    html = DirectionsText("de").markup("walk_to_stop", stop=stop_name("A <b> & B"))
    assert isinstance(html, Markup)
    assert "A &lt;b&gt; &amp; B" in html and '<img class="stop-symbol"' in html


class _Leg:
    def __init__(self, mode, kind="transit"):
        self.mode, self.kind = mode, kind


def test_transit_modes_names_the_means_of_transport_used():
    from app.i18n import DirectionsText

    walk = _Leg("WALK", "walk")
    de = DirectionsText("de")
    assert de.transit_modes([walk, _Leg("BUS"), walk]) == "Mit Bus"
    assert de.transit_modes([_Leg("REGIONAL_RAIL"), _Leg("BUS")]) == "Mit Bus und Bahn"
    assert de.transit_modes([_Leg("BUS"), _Leg("FERRY"), _Leg("TRAM")]) == "Mit Bus, Straßenbahn und Fähre"
    assert de.transit_modes([_Leg("BUS"), _Leg("COACH")]) == "Mit Bus"   # same kind once
    assert DirectionsText("en").transit_modes([_Leg("BUS"), _Leg("RAIL")]) == "By bus and train"
    assert DirectionsText("pl").transit_modes([_Leg("BUS"), _Leg("RAIL")]) == "Autobusem i pociągiem"
    assert DirectionsText("ar").transit_modes([_Leg("BUS"), _Leg("RAIL")]) == "بالحافلة والقطار"
    # unknown mode or no ride: generic text
    assert de.transit_modes([_Leg("OTHER")]) == "Mit Bus und Bahn" == de("transit")
    assert de.transit_modes([walk]) == de("transit")


def test_every_directions_language_has_a_transit_mode_phrase():
    from app.i18n import DIRECTIONS_LANGUAGES, TRANSIT_KINDS, TRANSIT_MODE_PHRASES

    for lang in DIRECTIONS_LANGUAGES:
        template, nouns, _sep, _last = TRANSIT_MODE_PHRASES[lang]
        assert "{modes}" in template and len(nouns) == len(TRANSIT_KINDS), lang
