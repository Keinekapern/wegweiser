"""Admin login and who may change what.

All permission checks go through can() / require(), so a later mode with user accounts
and roles per location only has to change this module and the database.

Modes (AUTH_MODE): "admin" (default, described below) and "off" (no login at all,
everyone may do everything; for a single PC or a small trusted network).

- Admins log in with username + password (scrypt hash, stdlib only). The session is a
  random token in an HttpOnly cookie; only its SHA-256 is stored (admin_sessions).
- Without login anyone may create destinations; they stay "pending" until an admin
  approves them. The creating browser gets a random creator cookie, so it can still
  correct its own pending destinations.
- Cookies are SameSite=Lax and every change is a POST, so other sites cannot trigger
  changes in a logged-in browser.
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
SESSION_HOURS = 12
CREATOR_COOKIE_DAYS = 365
MIN_PASSWORD_LENGTH = 10

# scrypt parameters (OWASP minimum: N=2^17, r=8, p=1 needs 128 MB; 2^15 keeps memory at 32 MB)
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 64 * 1024 * 1024


class LoginRequired(Exception):
    """Raised by require_admin; main.py turns it into a redirect to the login page."""

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


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> db.Admin | None:
    found = db.get_admin_credentials(conn, username.strip())
    if found is None:
        verify_password(password, _DUMMY_HASH)
        return None
    admin, stored = found
    return admin if verify_password(password, stored) else None


# --- current admin / creator ---

def current_admin(request: Request) -> db.Admin | None:
    """Logged-in admin of this request (cached on request.state); never one without login."""
    if hasattr(request.state, "admin"):
        return request.state.admin
    admin = None
    token = request.cookies.get(SESSION_COOKIE)
    if token and login_enabled():
        with db.get_conn() as conn:
            admin = db.session_admin(conn, token_hash(token))
    request.state.admin = admin
    return admin


def require_admin(request: Request) -> db.Admin:
    """FastAPI dependency: the logged-in admin, otherwise redirect to the login page
    (404 when login is switched off)."""
    if not login_enabled():
        raise HTTPException(404)
    admin = current_admin(request)
    if admin is None:
        next_url = request.url.path if request.method == "GET" else "/admin"
        if request.method == "GET" and request.url.query:
            next_url += "?" + request.url.query
        raise LoginRequired(next_url)
    return admin


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
    "admin.panel",                   # admin page: approvals, admin accounts
)


def login_enabled() -> bool:
    return config.auth_mode() != "off"


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


def can(request: Request, action: str, obj=None, conn: sqlite3.Connection | None = None) -> bool:
    """May the current browser do this? The single place that decides."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    if not login_enabled():
        return action != "admin.panel"   # nothing to administer without accounts
    if action == "destination.create":
        return True
    if current_admin(request) is not None:
        return True
    if action in ("destination.edit", "destination.delete"):
        return obj is not None and _own_pending(request, conn, obj)
    return False


def require(request: Request, action: str, obj=None, conn: sqlite3.Connection | None = None) -> None:
    """Raise unless allowed: login page if logging in could help, otherwise 404."""
    if can(request, action, obj, conn):
        return
    if login_enabled() and current_admin(request) is None:
        require_admin(request)            # raises LoginRequired
    raise HTTPException(404)


def creates_pending(request: Request) -> bool:
    """New destinations from this browser wait for approval."""
    return login_enabled() and current_admin(request) is None


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
