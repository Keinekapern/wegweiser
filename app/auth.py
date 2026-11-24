"""Login and who may change what.

All permission checks go through can() / require(); routes and templates never look at
roles themselves.

Modes (AUTH_MODE):
- "off": no login at all, everyone may do everything (a single PC or a small trusted network).
- "admin" (default): without login anyone may create directions and destinations; new
  destinations stay "pending" until an admin approves them. The creating browser gets a
  random creator cookie, so it can still correct its own pending destinations.
- "users": everyone logs in. Roles (db.ROLES):
    admin    everything, incl. accounts, locations and settings
    manager  edit, delete and approve the destinations of their own locations (those
             assigned only to locations of this account; destinations for all locations
             are left to admins); their new destinations are approved at once
    staff    directions, PDFs, propose destinations (pending, assigned to their locations)
  Everybody sees all locations and destinations; their own location is preselected.

Accounts log in with username + password (scrypt hash, stdlib only). The session is a
random token in an HttpOnly cookie; only its SHA-256 is stored (admin_sessions). Cookies
are SameSite=Lax and every change is a POST, so other sites cannot trigger changes in a
logged-in browser. New accounts get a start password that must be changed at first login.
"""

import hashlib
import hmac
import secrets
import sqlite3
import time
from urllib.parse import quote

from fastapi import HTTPException, Request

from app import config, db

SESSION_COOKIE = "wegweiser_admin"
CREATOR_COOKIE = "wegweiser_creator"
RENDER_COOKIE = "wegweiser_render"
SESSION_HOURS = 12
CREATOR_COOKIE_DAYS = 365
MIN_PASSWORD_LENGTH = 10

# scrypt parameters (OWASP minimum: N=2^17, r=8, p=1 needs 128 MB; 2^15 keeps memory at 32 MB)
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 64 * 1024 * 1024


class LoginRequired(Exception):
    """Raised by require_login; main.py turns it into a redirect to the login page."""

    def __init__(self, next_url: str = "/admin"):
        self.next_url = next_url


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r),
                                p=int(p), maxmem=_MAXMEM, dklen=len(bytes.fromhex(key)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual.hex(), key)


# Verifying against this for unknown usernames keeps the response time the same
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- brute-force protection (per process; enough for a small self-hosted instance) ---

_MAX_FAILURES = 5
_LOCK_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}


def login_locked(username: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(username.lower(), []) if now - t < _LOCK_SECONDS]
    _failures[username.lower()] = recent
    return len(recent) >= _MAX_FAILURES


def record_failure(username: str) -> None:
    _failures.setdefault(username.lower(), []).append(time.monotonic())


def clear_failures(username: str) -> None:
    _failures.pop(username.lower(), None)


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> db.Account | None:
    found = db.get_account_credentials(conn, username.strip())
    if found is None:
        verify_password(password, _DUMMY_HASH)
        return None
    admin, stored = found
    return admin if verify_password(password, stored) else None


# --- current account / creator / PDF renderer ---

def current_user(request: Request) -> db.Account | None:
    """Logged-in account of this request (cached on request.state); never one without login."""
    if hasattr(request.state, "user"):
        return request.state.user
    user = None
    token = request.cookies.get(SESSION_COOKIE)
    if token and login_enabled():
        with db.get_conn() as conn:
            user = db.session_account(conn, token_hash(token))
    request.state.user = user
    return user


def require_login(request: Request) -> db.Account:
    """FastAPI dependency: the logged-in account, otherwise redirect to the login page
    (404 when login is switched off)."""
    if not login_enabled():
        raise HTTPException(404)
    user = current_user(request)
    if user is None:
        raise LoginRequired(_here(request))
    return user


def _here(request: Request) -> str:
    if request.method != "GET":
        return "/admin"
    return request.url.path + ("?" + request.url.query if request.url.query else "")


# The server-side PDF renderer (app/services/pdf.py) opens the print view without a login;
# in AUTH_MODE=users it presents this per-process secret as a cookie instead.
_RENDER_TOKEN = secrets.token_urlsafe(32)


def render_token() -> str:
    return _RENDER_TOKEN


def is_renderer(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(RENDER_COOKIE, ""), _RENDER_TOKEN)


# Pages that work without login in AUTH_MODE=users and during a forced password change
_OPEN_PREFIXES = ("/static/", "/regions/")
_OPEN_PATHS = {"/admin/login", "/admin/logout", "/healthz", "/favicon.ico", "/ui-language/de",
               "/ui-language/en"}
_PASSWORD_PATHS = {"/admin", "/admin/password", "/admin/logout"}


def gate(request: Request) -> str | None:
    """Called for every request (main.py): where to send the browser instead, or None.
    AUTH_MODE=users: only the login page without login; any mode: an account with a start
    password may only change it."""
    path = request.url.path
    if not login_enabled() or path.startswith(_OPEN_PREFIXES) or path in _OPEN_PATHS:
        return None
    user = current_user(request)
    if user is None:
        if login_required() and not (request.method == "GET" and is_renderer(request)):
            return login_url(_here(request))
        return None
    if user.must_change_password and path not in _PASSWORD_PATHS:
        return "/admin"
    return None


def login_url(next_url: str) -> str:
    return "/admin/login?next=" + quote(next_url, safe="")


def creator_hash(request: Request) -> str | None:
    token = request.cookies.get(CREATOR_COOKIE)
    return token_hash(token) if token else None


def ensure_creator_token(request: Request) -> tuple[str, str | None]:
    """(hash to store, new cookie value or None if the browser already has one)"""
    token = request.cookies.get(CREATOR_COOKIE)
    if token and 20 <= len(token) <= 100:
        return token_hash(token), None
    token = secrets.token_urlsafe(32)
    return token_hash(token), token


# --- permissions ---

ACTIONS = (
    "destination.create",            # everyone; without admin rights the destination is pending
    "destination.edit",              # obj = destination
    "destination.delete",            # obj = destination
    "destination.assign_locations",  # choose the locations a destination is offered for
    "destination.approve",
    "location.manage",               # create, edit, delete locations
    "settings.transit_defaults",
    "settings.languages",            # which directions languages are offered
    "settings.print",                # printout options (e.g. the Wegweiser credit)
    "settings.backup",               # list, create and download database backups
    "data.transfer",                 # export and import destinations and locations
    "admin.panel",                   # account page: own password, approvals
    "accounts.manage",               # create, change and delete accounts
    "export.pdf",                    # a single PDF of a printout
    "export.bulk",                   # ZIP of many PDFs (server load, tile requests)
)


def login_enabled() -> bool:
    return config.auth_mode() != "off"


def login_required() -> bool:
    return config.auth_mode() == "users"


def _dest_locations(conn: sqlite3.Connection | None, dest: db.Destination) -> list[int]:
    if conn is None:
        with db.get_conn() as c:
            return db.locations_of_destination(c, dest.id)
    return db.locations_of_destination(conn, dest.id)


def _own_pending(request: Request, conn: sqlite3.Connection | None, dest: db.Destination) -> bool:
    if not dest.pending:
        return False
    mine = creator_hash(request)
    if not mine:
        return False
    if conn is None:
        with db.get_conn() as c:
            stored = db.destination_creator_token(c, dest.id)
    else:
        stored = db.destination_creator_token(conn, dest.id)
    return bool(stored and hmac.compare_digest(mine, stored))


def manages(user: db.Account | None, location_ids) -> bool:
    """Is this a manager of all these locations (at least one; "all locations" = admins)?"""
    return (user is not None and user.role == "manager" and bool(location_ids)
            and set(location_ids) <= set(user.location_ids))


def can(request: Request, action: str, obj=None, conn: sqlite3.Connection | None = None) -> bool:
    """May the current browser do this? The single place that decides."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    if not login_enabled():
        return action not in ("admin.panel", "accounts.manage")   # no accounts without login
    user = current_user(request)
    if user is None:
        if login_required():
            return False
        if action in ("destination.create", "export.pdf"):
            return True
        if action in ("destination.edit", "destination.delete"):
            return obj is not None and _own_pending(request, conn, obj)
        return False
    if user.is_admin:
        return True
    if action in ("destination.create", "export.pdf", "admin.panel"):
        return True
    if action in ("destination.edit", "destination.delete", "destination.approve"):
        if obj is None:
            return False
        if manages(user, _dest_locations(conn, obj)):
            return True
        return action != "destination.approve" and _own_pending(request, conn, obj)
    if action == "destination.assign_locations":
        return user.role == "manager"
    return False


def require(request: Request, action: str, obj=None, conn: sqlite3.Connection | None = None) -> None:
    """Raise unless allowed: login page if logging in could help, otherwise 404."""
    if can(request, action, obj, conn):
        return
    if login_enabled() and current_user(request) is None:
        require_login(request)            # raises LoginRequired
    raise HTTPException(404)


def creates_pending(request: Request) -> bool:
    """New destinations from this browser wait for approval (not for admins and managers)."""
    if not login_enabled():
        return False
    user = current_user(request)
    return user is None or user.role == "staff"


def assignable_locations(request: Request) -> set[int] | None:
    """Locations this browser may assign destinations to: None = any, otherwise these."""
    user = current_user(request)
    if not login_enabled() or (user is not None and user.is_admin):
        return None
    return set(user.location_ids) if user is not None else set()


def home_locations(request: Request) -> tuple[int, ...]:
    """Locations of the logged-in account (preselected in the location menus)."""
    user = current_user(request)
    return user.location_ids if user is not None else ()


def secure_cookies(request: Request) -> bool:
    return request.url.scheme == "https"


def set_cookie(response, request: Request, name: str, value: str, max_age: int) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, samesite="lax",
                        secure=secure_cookies(request), path="/")


def safe_next(next_url: str | None) -> str:
    """Only local paths, no open redirect ("//evil", "https://evil", "/\\evil")."""
    if not next_url or not next_url.startswith("/") or next_url.startswith(("//", "/\\")):
        return "/admin"
    return next_url
