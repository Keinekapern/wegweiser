"""SQLite access. Schema changes are applied via PRAGMA user_version migrations."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app.config import database_path

MIGRATIONS: list[str] = [
    # 1: locations (fixed start points)
    """
    CREATE TABLE locations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        address    TEXT    NOT NULL,
        lat        REAL    NOT NULL CHECK (lat BETWEEN -90 AND 90),
        lon        REAL    NOT NULL CHECK (lon BETWEEN -180 AND 180),
        created_at TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 2: destinations + geocoding cache
    """
    CREATE TABLE destinations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        address         TEXT    NOT NULL,
        lat             REAL    NOT NULL CHECK (lat BETWEEN -90 AND 90),
        lon             REAL    NOT NULL CHECK (lon BETWEEN -180 AND 180),
        phone           TEXT    NOT NULL DEFAULT '',
        website         TEXT    NOT NULL DEFAULT '',
        opening_hours   TEXT    NOT NULL DEFAULT '',
        google_maps_url TEXT    NOT NULL DEFAULT '',
        note            TEXT    NOT NULL DEFAULT '',
        osm_type        TEXT    CHECK (osm_type IN ('node', 'way', 'relation')),
        osm_id          INTEGER,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE geocode_cache (
        cache_key  TEXT PRIMARY KEY,
        response   TEXT NOT NULL,
        fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 3: generic API cache (geocoding + routing) and daily API usage counter
    """
    ALTER TABLE geocode_cache RENAME TO api_cache;
    CREATE TABLE api_usage (
        service TEXT NOT NULL,
        day     TEXT NOT NULL,
        count   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (service, day)
    );
    """,
    # 4: key/value settings (e.g. public transport defaults)
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 5: line symbols (pictograms shown next to line numbers, e.g. TüBus Tübingen)
    """
    CREATE TABLE line_symbol_sets (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL,
        modes   TEXT NOT NULL DEFAULT 'BUS',   -- comma-separated MOTIS modes
        min_lat REAL NOT NULL, min_lon REAL NOT NULL,
        max_lat REAL NOT NULL, max_lon REAL NOT NULL,
        credit  TEXT NOT NULL DEFAULT ''       -- attribution shown on the printout
    );
    CREATE TABLE line_symbols (
        set_id INTEGER NOT NULL REFERENCES line_symbol_sets(id) ON DELETE CASCADE,
        line   TEXT NOT NULL,
        label  TEXT NOT NULL,
        image  TEXT NOT NULL,                  -- path below app/static
        PRIMARY KEY (set_id, line)
    );
    -- Tübingen city buses (TüBus): line -> motif as on the bus displays,
    -- see tuebus.de "Übersicht der Symbole". Free Twemoji graphics with the same motifs.
    INSERT INTO line_symbol_sets (id, name, modes, min_lat, min_lon, max_lat, max_lon, credit)
    VALUES (1, 'TüBus Tübingen', 'BUS', 48.45, 8.93, 48.59, 9.15, 'Twemoji (CC BY 4.0)');
    INSERT INTO line_symbols (set_id, line, label, image) VALUES
        (1, '1', 'Katze', 'vendor/twemoji-17.0.3/1f408.svg'),
        (1, '2', 'Haus', 'vendor/twemoji-17.0.3/1f3e0.svg'),
        (1, '3', 'Ball', 'vendor/twemoji-17.0.3/26bd.svg'),
        (1, '4', 'Blatt', 'vendor/twemoji-17.0.3/1f341.svg'),
        (1, '5', 'Kreuz', 'vendor/twemoji-17.0.3/2795.svg'),
        (1, '6', 'Tanne', 'vendor/twemoji-17.0.3/1f332.svg'),
        (1, '7', 'Eichhörnchen', 'vendor/twemoji-17.0.3/1f43f.svg'),
        (1, '8', 'Tasse', 'vendor/twemoji-17.0.3/2615.svg'),
        (1, '9', 'Schloss', 'vendor/twemoji-17.0.3/1f3f0.svg'),
        (1, '10', 'Gockel', 'vendor/twemoji-17.0.3/1f413.svg'),
        (1, '11', 'Kerze', 'vendor/twemoji-17.0.3/1f56f.svg'),
        (1, '12', 'Birne', 'vendor/twemoji-17.0.3/1f350.svg'),
        (1, '13', 'Elefant', 'vendor/twemoji-17.0.3/1f418.svg'),
        (1, '14', 'Koffer', 'vendor/twemoji-17.0.3/1f4bc.svg'),
        (1, '15', 'Glas', 'vendor/twemoji-17.0.3/1f377.svg'),
        (1, '16', 'Schirm', 'vendor/twemoji-17.0.3/2602.svg'),
        (1, '17', 'Glühbirne', 'vendor/twemoji-17.0.3/1f4a1.svg'),
        (1, '18', 'Kapelle', 'vendor/twemoji-17.0.3/26ea.svg'),
        (1, '19', 'Brief', 'vendor/twemoji-17.0.3/2709.svg'),
        (1, '21', 'Schere', 'vendor/twemoji-17.0.3/2702.svg'),
        (1, '22', 'Fisch', 'vendor/twemoji-17.0.3/1f41f.svg'),
        (1, '31', 'Kleeblatt', 'vendor/twemoji-17.0.3/2618.svg'),
        (1, '32', 'Palme', 'vendor/twemoji-17.0.3/1f334.svg'),
        (1, '33', 'Zelt', 'vendor/twemoji-17.0.3/26fa.svg'),
        (1, '34', 'Baum', 'vendor/twemoji-17.0.3/1f333.svg'),
        (1, '35', 'Lokomotive', 'vendor/twemoji-17.0.3/1f682.svg');
    """,
    # 6: destinations <-> locations (many-to-many). Destinations without any
    # assignment are offered for all locations.
    """
    CREATE TABLE destination_locations (
        destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
        location_id    INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        PRIMARY KEY (destination_id, location_id)
    );
    CREATE INDEX destination_locations_by_location ON destination_locations(location_id);
    -- With exactly one location, existing destinations obviously belong to it
    INSERT INTO destination_locations (destination_id, location_id)
        SELECT d.id, l.id FROM destinations d, locations l
        WHERE (SELECT COUNT(*) FROM locations) = 1;
    """,
    # 7: destination category (key from app/categories.py, '' = none)
    """
    ALTER TABLE destinations ADD COLUMN category TEXT NOT NULL DEFAULT '';
    """,
    # 8: own single-colour symbols (static/symbols/, coloured like the line number)
    """
    UPDATE line_symbols SET image = 'symbols/cross-roof.svg'
        WHERE image = 'vendor/twemoji-17.0.3/2795.svg';
    """,
    # 9: all TüBus line symbols are own single-colour drawings (no Twemoji credit needed)
    """
    UPDATE line_symbols SET image = CASE line
            WHEN '1' THEN 'symbols/cat.svg'
            WHEN '2' THEN 'symbols/house.svg'
            WHEN '3' THEN 'symbols/ball.svg'
            WHEN '4' THEN 'symbols/leaf.svg'
            WHEN '6' THEN 'symbols/fir.svg'
            WHEN '7' THEN 'symbols/squirrel.svg'
            WHEN '8' THEN 'symbols/cup.svg'
            WHEN '9' THEN 'symbols/castle.svg'
            WHEN '10' THEN 'symbols/rooster.svg'
            WHEN '11' THEN 'symbols/candle.svg'
            WHEN '12' THEN 'symbols/pear.svg'
            WHEN '13' THEN 'symbols/elephant.svg'
            WHEN '14' THEN 'symbols/suitcase.svg'
            WHEN '15' THEN 'symbols/glass.svg'
            WHEN '16' THEN 'symbols/umbrella.svg'
            WHEN '17' THEN 'symbols/bulb.svg'
            WHEN '18' THEN 'symbols/chapel.svg'
            WHEN '19' THEN 'symbols/letter.svg'
            WHEN '21' THEN 'symbols/scissors.svg'
            WHEN '22' THEN 'symbols/fish.svg'
            WHEN '31' THEN 'symbols/clover.svg'
            WHEN '32' THEN 'symbols/palm.svg'
            WHEN '33' THEN 'symbols/tent.svg'
            WHEN '34' THEN 'symbols/tree.svg'
            WHEN '35' THEN 'symbols/locomotive.svg'
            ELSE image END
        WHERE set_id = (SELECT id FROM line_symbol_sets WHERE name = 'TüBus Tübingen')
          AND image LIKE 'vendor/twemoji-%';
    UPDATE line_symbol_sets SET credit = '' WHERE name = 'TüBus Tübingen'
        AND NOT EXISTS (SELECT 1 FROM line_symbols s WHERE s.set_id = line_symbol_sets.id
                        AND s.image LIKE 'vendor/twemoji-%');
    """,
    # 10: destination names in other languages (directions language code, e.g. 'en', 'ar')
    """
    CREATE TABLE destination_names (
        destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
        lang           TEXT NOT NULL,
        name           TEXT NOT NULL,
        PRIMARY KEY (destination_id, lang)
    );
    """,
    # 11: admin accounts + sessions; destinations created without login wait for approval.
    # creator_token = SHA-256 of the creating browser's random cookie (lets the creator
    # correct a pending destination), approved_by = admin username.
    """
    CREATE TABLE admins (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE admin_sessions (
        token_hash TEXT PRIMARY KEY,
        admin_id   INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL
    );
    ALTER TABLE destinations ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved', 'pending'));
    ALTER TABLE destinations ADD COLUMN creator_token TEXT;
    ALTER TABLE destinations ADD COLUMN approved_by TEXT NOT NULL DEFAULT '';
    """,
    # 12: line symbols are no longer in the database but in regional add-ons
    # (app/regions/<key>/region.json, see app/regions.py)
    """
    DROP TABLE line_symbols;
    DROP TABLE line_symbol_sets;
    """,
    # 13: accounts get a role and locations (AUTH_MODE=users, see app/auth.py). The tables
    # keep their old names "admins"/"admin_sessions"; existing accounts become admins.
    """
    ALTER TABLE admins ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'
        CHECK (role IN ('admin', 'manager', 'staff'));
    ALTER TABLE admins ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE admin_locations (
        admin_id    INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        PRIMARY KEY (admin_id, location_id)
    );
    """,
]


@dataclass
class Location:
    id: int
    name: str
    address: str
    lat: float
    lon: float


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may create it in a worker thread and use it
    # in the event loop thread (async endpoints), never concurrently.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        migrate(conn)
        normalize_existing_phones(conn)


def normalize_existing_phones(conn: sqlite3.Connection) -> None:
    """One-off: bring phone numbers saved before normalization into +49 format."""
    from app.validation import normalize_phone   # avoid import cycle at module load
    if setting_get(conn, "phones_normalized_v1"):
        return
    with conn:
        for row in conn.execute("SELECT id, phone FROM destinations WHERE phone != ''").fetchall():
            phone = normalize_phone(row["phone"])
            if phone != row["phone"]:
                conn.execute("UPDATE destinations SET phone = ? WHERE id = ?", (phone, row["id"]))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('phones_normalized_v1', '1')")


# --- locations -------------------------------------------------------------

def _row_to_location(row: sqlite3.Row) -> Location:
    return Location(row["id"], row["name"], row["address"], row["lat"], row["lon"])


def list_locations(conn: sqlite3.Connection) -> list[Location]:
    rows = conn.execute(
        "SELECT id, name, address, lat, lon FROM locations ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [_row_to_location(r) for r in rows]


def get_location(conn: sqlite3.Connection, location_id: int) -> Location | None:
    row = conn.execute(
        "SELECT id, name, address, lat, lon FROM locations WHERE id = ?", (location_id,)
    ).fetchone()
    return _row_to_location(row) if row else None


def create_location(conn: sqlite3.Connection, name: str, address: str, lat: float, lon: float) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO locations (name, address, lat, lon) VALUES (?, ?, ?, ?)",
            (name, address, lat, lon),
        )
    return cur.lastrowid


def update_location(
    conn: sqlite3.Connection, location_id: int, name: str, address: str, lat: float, lon: float
) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE locations SET name = ?, address = ?, lat = ?, lon = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (name, address, lat, lon, location_id),
        )
    return cur.rowcount > 0


def delete_location(conn: sqlite3.Connection, location_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    return cur.rowcount > 0


# --- destinations ----------------------------------------------------------

@dataclass
class Destination:
    id: int | None
    name: str
    address: str
    lat: float
    lon: float
    phone: str = ""
    website: str = ""
    opening_hours: str = ""
    google_maps_url: str = ""
    note: str = ""
    osm_type: str | None = None
    osm_id: int | None = None
    category: str = ""
    # set by the approval workflow, not by the destination form
    status: str = "approved"

    @property
    def pending(self) -> bool:
        return self.status == "pending"

    @property
    def osm_url(self) -> str | None:
        if self.osm_type and self.osm_id:
            return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"
        return None


# Columns written by the destination form (status only via create/approve)
_DEST_COLUMNS = [f.name for f in fields(Destination) if f.name not in ("id", "status")]
_DEST_SELECT = ", ".join(["id", *_DEST_COLUMNS, "status"])


def list_destinations(conn: sqlite3.Connection,
                      location_id: int | None = None) -> list[Destination]:
    """All destinations, or those offered for a location (assigned to it or unassigned)."""
    sql = f"SELECT {_DEST_SELECT} FROM destinations d"
    params: tuple = ()
    if location_id is not None:
        sql += (" WHERE NOT EXISTS (SELECT 1 FROM destination_locations dl"
                "                   WHERE dl.destination_id = d.id)"
                " OR EXISTS (SELECT 1 FROM destination_locations dl"
                "            WHERE dl.destination_id = d.id AND dl.location_id = ?)")
        params = (location_id,)
    rows = conn.execute(sql + " ORDER BY name COLLATE NOCASE", params).fetchall()
    return [Destination(**dict(r)) for r in rows]


def destination_location_ids(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """destination id -> assigned location ids (missing/empty = all locations)."""
    result: dict[int, list[int]] = {}
    for r in conn.execute("SELECT destination_id, location_id FROM destination_locations "
                          "ORDER BY location_id"):
        result.setdefault(r["destination_id"], []).append(r["location_id"])
    return result


def locations_of_destination(conn: sqlite3.Connection, destination_id: int) -> list[int]:
    return [r[0] for r in conn.execute("SELECT location_id FROM destination_locations"
                                       " WHERE destination_id = ? ORDER BY location_id",
                                       (destination_id,))]


def set_destination_locations(conn: sqlite3.Connection, destination_id: int,
                              location_ids: list[int]) -> None:
    with conn:
        conn.execute("DELETE FROM destination_locations WHERE destination_id = ?",
                     (destination_id,))
        conn.executemany(
            "INSERT INTO destination_locations (destination_id, location_id) "
            "SELECT ?, id FROM locations WHERE id = ?",   # ignores unknown location ids
            [(destination_id, lid) for lid in dict.fromkeys(location_ids)],
        )


def get_destination_names(conn: sqlite3.Connection, destination_id: int) -> dict[str, str]:
    """Translated names of a destination: {lang: name}."""
    rows = conn.execute("SELECT lang, name FROM destination_names WHERE destination_id = ?",
                        (destination_id,))
    return {row["lang"]: row["name"] for row in rows}


def set_destination_names(conn: sqlite3.Connection, destination_id: int,
                          names: dict[str, str]) -> None:
    """Sets the translated names of the given languages (empty = remove); names in other
    languages stay (e.g. languages currently switched off in the language settings)."""
    with conn:
        conn.executemany("DELETE FROM destination_names WHERE destination_id = ? AND lang = ?",
                         [(destination_id, lang) for lang in names])
        conn.executemany(
            "INSERT INTO destination_names (destination_id, lang, name) VALUES (?, ?, ?)",
            [(destination_id, lang, name.strip()) for lang, name in names.items() if name.strip()],
        )


def get_destination(conn: sqlite3.Connection, destination_id: int) -> Destination | None:
    row = conn.execute(
        f"SELECT {_DEST_SELECT} FROM destinations WHERE id = ?",
        (destination_id,),
    ).fetchone()
    return Destination(**dict(row)) if row else None


def create_destination(conn: sqlite3.Connection, dest: Destination, *,
                       pending: bool = False, creator_token: str | None = None) -> int:
    """pending: created without admin login, waits for approval; creator_token = hash
    of the creating browser's cookie."""
    values = asdict(dest)
    columns = [*_DEST_COLUMNS, "status", "creator_token"]
    placeholders = ", ".join("?" for _ in columns)
    with conn:
        cur = conn.execute(
            f"INSERT INTO destinations ({', '.join(columns)}) VALUES ({placeholders})",
            [values[c] for c in _DEST_COLUMNS]
            + ["pending" if pending else "approved", creator_token if pending else None],
        )
    return cur.lastrowid


def approve_destination(conn: sqlite3.Connection, destination_id: int, admin: str) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE destinations SET status = 'approved', creator_token = NULL, approved_by = ?,"
            " updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
            (admin, destination_id))
    return cur.rowcount > 0


def destination_creator_token(conn: sqlite3.Connection, destination_id: int) -> str | None:
    row = conn.execute("SELECT creator_token FROM destinations WHERE id = ?",
                       (destination_id,)).fetchone()
    return row[0] if row else None


def list_pending_destinations(conn: sqlite3.Connection) -> list[tuple[Destination, str]]:
    """Pending destinations with their creation time (UTC), oldest first."""
    rows = conn.execute(f"SELECT {_DEST_SELECT}, created_at FROM destinations"
                        " WHERE status = 'pending' ORDER BY created_at, id").fetchall()
    result = []
    for r in rows:
        data = dict(r)
        created = data.pop("created_at")
        result.append((Destination(**data), created))
    return result


def count_pending_destinations(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM destinations WHERE status = 'pending'").fetchone()[0]


# --- accounts (table "admins") ---

ROLES = ("admin", "manager", "staff")


@dataclass
class Account:
    id: int
    username: str
    role: str = "admin"
    location_ids: tuple[int, ...] = ()
    must_change_password: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_ACCOUNT_SELECT = "a.id, a.username, a.role, a.must_change_password"


def _accounts(conn: sqlite3.Connection, rows) -> list[Account]:
    rows = list(rows)
    locs: dict[int, list[int]] = {}
    if rows:
        ids = [r["id"] for r in rows]
        for r in conn.execute(
                f"SELECT admin_id, location_id FROM admin_locations WHERE admin_id IN"
                f" ({', '.join('?' for _ in ids)}) ORDER BY location_id", ids):
            locs.setdefault(r["admin_id"], []).append(r["location_id"])
    return [Account(r["id"], r["username"], r["role"], tuple(locs.get(r["id"], [])),
                    bool(r["must_change_password"])) for r in rows]


def account_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]


def admin_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM admins WHERE role = 'admin'").fetchone()[0]


def list_accounts(conn: sqlite3.Connection) -> list[Account]:
    return _accounts(conn, conn.execute(
        f"SELECT {_ACCOUNT_SELECT} FROM admins a ORDER BY a.username COLLATE NOCASE"))


def get_account(conn: sqlite3.Connection, account_id: int) -> Account | None:
    found = _accounts(conn, conn.execute(f"SELECT {_ACCOUNT_SELECT} FROM admins a WHERE a.id = ?",
                                         (account_id,)))
    return found[0] if found else None


def get_account_credentials(conn: sqlite3.Connection, username: str) -> tuple[Account, str] | None:
    row = conn.execute(f"SELECT {_ACCOUNT_SELECT}, a.password_hash FROM admins a WHERE a.username = ?",
                       (username,)).fetchone()
    return (_accounts(conn, [row])[0], row["password_hash"]) if row else None


def create_account(conn: sqlite3.Connection, username: str, password_hash: str, *,
                   role: str = "admin", location_ids: list[int] = (),
                   must_change_password: bool = False) -> int:
    with conn:
        cur = conn.execute("INSERT INTO admins (username, password_hash, role, must_change_password)"
                           " VALUES (?, ?, ?, ?)",
                           (username, password_hash, role, int(must_change_password)))
        _set_account_locations(conn, cur.lastrowid, location_ids)
    return cur.lastrowid


def _set_account_locations(conn: sqlite3.Connection, account_id: int, location_ids) -> None:
    conn.execute("DELETE FROM admin_locations WHERE admin_id = ?", (account_id,))
    conn.executemany("INSERT OR IGNORE INTO admin_locations (admin_id, location_id)"
                     " SELECT ?, id FROM locations WHERE id = ?",
                     [(account_id, i) for i in location_ids])


def update_account(conn: sqlite3.Connection, account_id: int, role: str,
                   location_ids: list[int]) -> bool:
    with conn:
        cur = conn.execute("UPDATE admins SET role = ? WHERE id = ?", (role, account_id))
        if cur.rowcount:
            _set_account_locations(conn, account_id, location_ids)
    return cur.rowcount > 0


def set_account_password(conn: sqlite3.Connection, account_id: int, password_hash: str, *,
                         must_change: bool = False) -> None:
    """New password; ends all sessions of the account."""
    with conn:
        conn.execute("UPDATE admins SET password_hash = ?, must_change_password = ? WHERE id = ?",
                     (password_hash, int(must_change), account_id))
        conn.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (account_id,))


def delete_account(conn: sqlite3.Connection, account_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM admins WHERE id = ?", (account_id,))
    return cur.rowcount > 0


def create_session(conn: sqlite3.Connection, token_hash: str, account_id: int, hours: int) -> None:
    with conn:
        conn.execute("DELETE FROM admin_sessions WHERE expires_at < datetime('now')")
        conn.execute("INSERT INTO admin_sessions (token_hash, admin_id, expires_at)"
                     " VALUES (?, ?, datetime('now', ?))", (token_hash, account_id, f"+{hours} hours"))


def session_account(conn: sqlite3.Connection, token_hash: str) -> Account | None:
    found = _accounts(conn, conn.execute(
        f"SELECT {_ACCOUNT_SELECT} FROM admin_sessions s JOIN admins a ON a.id = s.admin_id"
        " WHERE s.token_hash = ? AND s.expires_at > datetime('now')", (token_hash,)))
    return found[0] if found else None


def delete_session(conn: sqlite3.Connection, token_hash: str) -> None:
    with conn:
        conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,))


def update_destination(conn: sqlite3.Connection, destination_id: int, dest: Destination) -> bool:
    values = asdict(dest)
    assignments = ", ".join(f"{c} = ?" for c in _DEST_COLUMNS)
    with conn:
        cur = conn.execute(
            f"UPDATE destinations SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            [values[c] for c in _DEST_COLUMNS] + [destination_id],
        )
    return cur.rowcount > 0


def delete_destination(conn: sqlite3.Connection, destination_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM destinations WHERE id = ?", (destination_id,))
    return cur.rowcount > 0


# --- API cache and usage -------------------------------------------------------

def cache_get(conn: sqlite3.Connection, key: str, max_age_days: int) -> str | None:
    row = conn.execute(
        "SELECT response FROM api_cache WHERE cache_key = ? "
        "AND fetched_at >= datetime('now', ?)",
        (key, f"-{int(max_age_days)} days"),
    ).fetchone()
    return row["response"] if row else None


def cache_put(conn: sqlite3.Connection, key: str, response: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO api_cache (cache_key, response, fetched_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(cache_key) DO UPDATE SET response = excluded.response, "
            "fetched_at = excluded.fetched_at",
            (key, response),
        )


def usage_today(conn: sqlite3.Connection, service: str) -> int:
    row = conn.execute(
        "SELECT count FROM api_usage WHERE service = ? AND day = date('now')", (service,)
    ).fetchone()
    return row["count"] if row else 0


def usage_increment(conn: sqlite3.Connection, service: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO api_usage (service, day, count) VALUES (?, date('now'), 1) "
            "ON CONFLICT(service, day) DO UPDATE SET count = count + 1",
            (service,),
        )


# --- settings --------------------------------------------------------------

def setting_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def setting_put(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# --- line symbols ----------------------------------------------------------
