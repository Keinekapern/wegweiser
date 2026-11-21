"""Which directions languages are offered (language settings, admins).

Stored as a comma-separated list in the settings table; no setting = all languages.
German, the language of the data, is always on. Languages switched off disappear from
the directions page, the export and the destination form; links with such a language
fall back to German. The translation check page still shows all, so a language can be
proofread before it is switched on.
"""

import sqlite3

from app import db
from app.i18n import DEFAULT_DIRECTIONS_LANG, DIRECTIONS_LANGUAGES, directions_language_options

SETTING_KEY = "directions_languages"


def enabled(conn: sqlite3.Connection) -> list[str]:
    raw = db.setting_get(conn, SETTING_KEY)
    if raw is None:
        return list(DIRECTIONS_LANGUAGES)
    chosen = {c for c in raw.split(",") if c in DIRECTIONS_LANGUAGES}
    return [c for c in DIRECTIONS_LANGUAGES if c in chosen or c == DEFAULT_DIRECTIONS_LANG]


def set_enabled(conn: sqlite3.Connection, codes) -> list[str]:
    chosen = [c for c in DIRECTIONS_LANGUAGES if c in set(codes) or c == DEFAULT_DIRECTIONS_LANG]
    db.setting_put(conn, SETTING_KEY, ",".join(chosen))
    return chosen


def options(conn: sqlite3.Connection, ui_lang: str) -> dict[str, tuple[str, str]]:
    """Like i18n.directions_language_options, only the enabled languages."""
    on = set(enabled(conn))
    return {c: v for c, v in directions_language_options(ui_lang).items() if c in on}


def normalize(conn: sqlite3.Connection, lang: str | None) -> str:
    return lang if lang in set(enabled(conn)) else DEFAULT_DIRECTIONS_LANG
