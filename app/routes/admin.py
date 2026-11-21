"""Admin panel: login, destinations awaiting approval, admin accounts."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth, db
from app.deps import DB, AdminUser, templates
from app.i18n import Msg, get_ui_lang, translate

router = APIRouter(prefix="/admin")


def _validate_new_password(password: str, repeat: str, errors: list) -> None:
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        errors.append(Msg("Das Passwort muss mindestens {n} Zeichen lang sein.",
                          n=auth.MIN_PASSWORD_LENGTH))
    elif password != repeat:
        errors.append(Msg("Die Passwörter stimmen nicht überein."))


def render_dashboard(request: Request, conn, admin: db.Admin, *, errors=None, notice=None,
                     status_code: int = 200):
    locations = db.list_locations(conn)
    return templates.TemplateResponse(request, "admin.html", {
        "pending": db.list_pending_destinations(conn),
        "assignments": db.destination_location_ids(conn),
        "location_names": {loc.id: loc.name for loc in locations},
        "admins": db.list_admins(conn),
        "me": admin,
        "errors": errors or [],
        "notice": notice,
        "min_password": auth.MIN_PASSWORD_LENGTH,
    }, status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, conn: DB, next: str = "/admin"):
    if not auth.login_enabled():
        raise HTTPException(404)
    if auth.current_admin(request) is not None:
        return RedirectResponse(auth.safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", {
        "next": auth.safe_next(next), "error": None, "username": "",
        "no_admins": db.admin_count(conn) == 0,
    })


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
        admin = auth.authenticate(conn, username, password)
        if admin is None:
            auth.record_failure(username)
            error = Msg("Benutzername oder Passwort ist falsch.")
    if error is not None:
        return templates.TemplateResponse(request, "admin_login.html", {
            "next": auth.safe_next(next), "error": error, "username": username,
            "no_admins": db.admin_count(conn) == 0,
        }, status_code=401)
    auth.clear_failures(username)
    token = secrets.token_urlsafe(32)
    db.create_session(conn, auth.token_hash(token), admin.id, auth.SESSION_HOURS)
    response = RedirectResponse(auth.safe_next(next), status_code=303)
    auth.set_cookie(response, request, auth.SESSION_COOKIE, token, auth.SESSION_HOURS * 3600)
    return response


@router.post("/logout")
def logout(request: Request, conn: DB):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        db.delete_session(conn, auth.token_hash(token))
    response = RedirectResponse("/directions", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, conn: DB, admin: AdminUser):
    return render_dashboard(request, conn, admin)


@router.post("/destinations/{destination_id}/approve")
def approve(request: Request, conn: DB, admin: AdminUser, destination_id: int):
    auth.require(request, "destination.approve")
    if not db.approve_destination(conn, destination_id, admin.username):
        raise HTTPException(404, translate(get_ui_lang(request), "Ziel nicht gefunden"))
    return RedirectResponse("/admin", status_code=303)


@router.post("/users", response_class=HTMLResponse)
def create_admin(request: Request, conn: DB, admin: AdminUser,
                 username: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
                 repeat: Annotated[str, Form()] = ""):
    errors: list = []
    username = username.strip()
    if not username or len(username) > 100:
        errors.append(Msg("Bitte einen Benutzernamen angeben."))
    elif db.get_admin_credentials(conn, username) is not None:
        errors.append(Msg("Diesen Benutzernamen gibt es schon."))
    _validate_new_password(password, repeat, errors)
    if errors:
        return render_dashboard(request, conn, admin, errors=errors, status_code=422)
    db.create_admin(conn, username, auth.hash_password(password))
    return render_dashboard(request, conn, admin,
                            notice=Msg("Admin „{name}“ angelegt.", name=username))


@router.post("/users/{admin_id}/delete", response_class=HTMLResponse)
def delete_admin(request: Request, conn: DB, admin: AdminUser, admin_id: int):
    if admin_id == admin.id:
        return render_dashboard(request, conn, admin, status_code=422,
                                errors=[Msg("Das eigene Konto kann nicht gelöscht werden.")])
    if not db.delete_admin(conn, admin_id):
        raise HTTPException(404)
    return RedirectResponse("/admin", status_code=303)


@router.post("/password", response_class=HTMLResponse)
def change_password(request: Request, conn: DB, admin: AdminUser,
                    current: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
                    repeat: Annotated[str, Form()] = ""):
    errors: list = []
    if auth.authenticate(conn, admin.username, current) is None:
        errors.append(Msg("Das bisherige Passwort ist falsch."))
    _validate_new_password(password, repeat, errors)
    if errors:
        return render_dashboard(request, conn, admin, errors=errors, status_code=422)
    db.set_admin_password(conn, admin.id, auth.hash_password(password))   # ends all sessions
    token = secrets.token_urlsafe(32)
    db.create_session(conn, auth.token_hash(token), admin.id, auth.SESSION_HOURS)
    response = render_dashboard(request, conn, admin, notice=Msg("Passwort geändert."))
    auth.set_cookie(response, request, auth.SESSION_COOKIE, token, auth.SESSION_HOURS * 3600)
    return response
