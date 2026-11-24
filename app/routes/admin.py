"""Account page: login, own password, destinations awaiting approval, accounts."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth, db
from app.deps import DB, LoggedIn, approvable_pending, templates
from app.i18n import Msg, get_ui_lang, translate

router = APIRouter(prefix="/admin")

ROLE_LABELS = {"admin": "Admin", "manager": "Standortverantwortlich", "staff": "Mitarbeitend"}
# no 0/O, 1/l/I: start passwords are read out or written down
_PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _validate_new_password(password: str, repeat: str, errors: list) -> None:
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        errors.append(Msg("Das Passwort muss mindestens {n} Zeichen lang sein.",
                          n=auth.MIN_PASSWORD_LENGTH))
    elif password != repeat:
        errors.append(Msg("Die Passwörter stimmen nicht überein."))


def _base_context(request: Request, conn, user: db.Account) -> dict:
    locations = db.list_locations(conn)
    return {
        "me": user,
        "locations": locations,
        "location_names": {loc.id: loc.name for loc in locations},
        "role_labels": ROLE_LABELS,
        "roles_enabled": auth.login_required(),
        "min_password": auth.MIN_PASSWORD_LENGTH,
    }


def render_dashboard(request: Request, conn, user: db.Account, *, errors=None, notice=None,
                     new_password: str | None = None, form: dict | None = None,
                     status_code: int = 200):
    return templates.TemplateResponse(request, "admin.html", {
        **_base_context(request, conn, user),
        "pending": approvable_pending(request, conn),
        "may_approve": user.is_admin or user.role == "manager",
        "assignments": db.destination_location_ids(conn),
        "accounts": db.list_accounts(conn) if auth.can(request, "accounts.manage") else [],
        "errors": errors or [],
        "notice": notice,
        "new_password": new_password,
        "form": form or {"role": "staff" if auth.login_required() else "admin", "location_ids": []},
    }, status_code=status_code)


def _login_context(conn, next_url: str, error=None, username: str = "") -> dict:
    return {"next": auth.safe_next(next_url), "error": error, "username": username,
            "no_admins": db.admin_count(conn) == 0}


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, conn: DB, next: str = "/admin"):
    if not auth.login_enabled():
        raise HTTPException(404)
    if auth.current_user(request) is not None:
        return RedirectResponse(auth.safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", _login_context(conn, next))


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, conn: DB, username: Annotated[str, Form()] = "",
          password: Annotated[str, Form()] = "", next: Annotated[str, Form()] = "/admin"):
    if not auth.login_enabled():
        raise HTTPException(404)
    username = username.strip()[:100]
    error = None
    if auth.login_locked(username):
        error = Msg("Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.")
    else:
        user = auth.authenticate(conn, username, password)
        if user is None:
            auth.record_failure(username)
            error = Msg("Benutzername oder Passwort ist falsch.")
    if error is not None:
        return templates.TemplateResponse(request, "admin_login.html",
                                          _login_context(conn, next, error, username),
                                          status_code=401)
    auth.clear_failures(username)
    token = secrets.token_urlsafe(32)
    db.create_session(conn, auth.token_hash(token), user.id, auth.SESSION_HOURS)
    target = "/admin" if user.must_change_password else auth.safe_next(next)
    response = RedirectResponse(target, status_code=303)
    auth.set_cookie(response, request, auth.SESSION_COOKIE, token, auth.SESSION_HOURS * 3600)
    return response


@router.post("/logout")
def logout(request: Request, conn: DB):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        db.delete_session(conn, auth.token_hash(token))
    response = RedirectResponse("/admin/login" if auth.login_required() else "/directions",
                                status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, conn: DB, user: LoggedIn):
    return render_dashboard(request, conn, user)


@router.post("/destinations/{destination_id}/approve")
def approve(request: Request, conn: DB, user: LoggedIn, destination_id: int):
    dest = db.get_destination(conn, destination_id)
    if dest is None:
        raise HTTPException(404, translate(get_ui_lang(request), "Ziel nicht gefunden"))
    auth.require(request, "destination.approve", dest, conn)
    if not db.approve_destination(conn, destination_id, user.username):
        raise HTTPException(404, translate(get_ui_lang(request), "Ziel nicht gefunden"))
    return RedirectResponse("/admin", status_code=303)


# --- accounts ---

def _read_role(conn, role: str, location_ids: list[str], errors: list) -> tuple[str, list[int]]:
    """Role and locations from the form; outside AUTH_MODE=users every account is an admin."""
    if not auth.login_required():
        return "admin", []
    if role not in db.ROLES:
        role = "staff"
    known = {loc.id for loc in db.list_locations(conn)}
    ids = sorted({int(i) for i in location_ids if i.isdigit() and int(i) in known})
    if role == "admin":
        ids = []
    elif not ids:
        errors.append(Msg("Bitte mindestens einen Standort wählen."))
    return role, ids


def _account(conn, account_id: int) -> db.Account:
    account = db.get_account(conn, account_id)
    if account is None:
        raise HTTPException(404)
    return account


def _last_admin(conn, account: db.Account) -> bool:
    return account.is_admin and db.admin_count(conn) <= 1


@router.post("/users", response_class=HTMLResponse)
def create_account(request: Request, conn: DB, user: LoggedIn,
                   username: Annotated[str, Form()] = "", role: Annotated[str, Form()] = "staff",
                   location_ids: Annotated[list[str], Form()] = [],
                   password: Annotated[str, Form()] = ""):
    auth.require(request, "accounts.manage")
    errors: list = []
    username = username.strip()
    if not username or len(username) > 100:
        errors.append(Msg("Bitte einen Benutzernamen angeben."))
    elif db.get_account_credentials(conn, username) is not None:
        errors.append(Msg("Diesen Benutzernamen gibt es schon."))
    role, ids = _read_role(conn, role, location_ids, errors)
    password = password.strip() or generate_password()
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        errors.append(Msg("Das Passwort muss mindestens {n} Zeichen lang sein.",
                          n=auth.MIN_PASSWORD_LENGTH))
    if errors:
        return render_dashboard(request, conn, user, errors=errors, status_code=422,
                                form={"username": username, "role": role, "location_ids": ids})
    db.create_account(conn, username, auth.hash_password(password), role=role, location_ids=ids,
                      must_change_password=True)
    return render_dashboard(request, conn, user, new_password=password,
                            notice=Msg("Konto „{name}“ angelegt. Startpasswort (bitte weitergeben, wird beim ersten Anmelden geändert):",
                                       name=username))


@router.get("/users/{account_id}", response_class=HTMLResponse)
def account_page(request: Request, conn: DB, user: LoggedIn, account_id: int):
    auth.require(request, "accounts.manage")
    return templates.TemplateResponse(request, "admin_account.html", {
        **_base_context(request, conn, user), "account": _account(conn, account_id),
        "errors": [], "notice": None, "new_password": None})


def _render_account(request, conn, user, account, *, errors=None, notice=None,
                    new_password=None, status_code=200):
    return templates.TemplateResponse(request, "admin_account.html", {
        **_base_context(request, conn, user), "account": account, "errors": errors or [],
        "notice": notice, "new_password": new_password}, status_code=status_code)


@router.post("/users/{account_id}", response_class=HTMLResponse)
def update_account(request: Request, conn: DB, user: LoggedIn, account_id: int,
                   role: Annotated[str, Form()] = "staff",
                   location_ids: Annotated[list[str], Form()] = []):
    auth.require(request, "accounts.manage")
    account = _account(conn, account_id)
    errors: list = []
    role, ids = _read_role(conn, role, location_ids, errors)
    if role != "admin" and account.id == user.id:
        errors.append(Msg("Die eigene Rolle kann nicht geändert werden."))
    elif role != "admin" and _last_admin(conn, account):
        errors.append(Msg("Es muss mindestens ein Admin-Konto geben."))
    if errors:
        return _render_account(request, conn, user, account, errors=errors, status_code=422)
    db.update_account(conn, account_id, role, ids)
    return RedirectResponse("/admin", status_code=303)


@router.post("/users/{account_id}/password", response_class=HTMLResponse)
def reset_password(request: Request, conn: DB, user: LoggedIn, account_id: int):
    auth.require(request, "accounts.manage")
    account = _account(conn, account_id)
    if account.id == user.id:
        raise HTTPException(404)          # own password: form with the current one
    password = generate_password()
    db.set_account_password(conn, account_id, auth.hash_password(password), must_change=True)
    return _render_account(request, conn, user, _account(conn, account_id), new_password=password,
                           notice=Msg("Neues Startpasswort (bitte weitergeben, wird beim ersten Anmelden geändert):"))


@router.post("/users/{account_id}/delete", response_class=HTMLResponse)
def delete_account(request: Request, conn: DB, user: LoggedIn, account_id: int):
    auth.require(request, "accounts.manage")
    account = _account(conn, account_id)
    if account.id == user.id:
        return render_dashboard(request, conn, user, status_code=422,
                                errors=[Msg("Das eigene Konto kann nicht gelöscht werden.")])
    if _last_admin(conn, account):
        return render_dashboard(request, conn, user, status_code=422,
                                errors=[Msg("Es muss mindestens ein Admin-Konto geben.")])
    db.delete_account(conn, account_id)
    return RedirectResponse("/admin", status_code=303)


@router.post("/password", response_class=HTMLResponse)
def change_password(request: Request, conn: DB, user: LoggedIn,
                    current: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
                    repeat: Annotated[str, Form()] = ""):
    errors: list = []
    if auth.authenticate(conn, user.username, current) is None:
        errors.append(Msg("Das bisherige Passwort ist falsch."))
    _validate_new_password(password, repeat, errors)
    if not errors and password == current:
        errors.append(Msg("Bitte ein neues Passwort wählen, nicht das bisherige."))
    if errors:
        return render_dashboard(request, conn, user, errors=errors, status_code=422)
    db.set_account_password(conn, user.id, auth.hash_password(password))   # ends all sessions
    token = secrets.token_urlsafe(32)
    db.create_session(conn, auth.token_hash(token), user.id, auth.SESSION_HOURS)
    user = db.get_account(conn, user.id)
    request.state.user = user
    response = render_dashboard(request, conn, user, notice=Msg("Passwort geändert."))
    auth.set_cookie(response, request, auth.SESSION_COOKIE, token, auth.SESSION_HOURS * 3600)
    return response
