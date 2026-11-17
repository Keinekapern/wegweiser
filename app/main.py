from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import config, db
from app.auth import LoginRequired, login_url
from app.deps import BASE_DIR
from app.routes import admin, api, destinations, directions, locations, translations, ui


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)


@app.exception_handler(LoginRequired)
async def login_required(_request: Request, exc: LoginRequired):
    return RedirectResponse(login_url(exc.next_url), status_code=303)


class RevalidatedStaticFiles(StaticFiles):
    """Static files the browser must revalidate (ETag) before use, so an update of
    JS/CSS takes effect on the next page load instead of after a heuristic cache time."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatedStaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(locations.router)
app.include_router(destinations.router)
app.include_router(directions.router)
app.include_router(api.router)
app.include_router(ui.router)
app.include_router(translations.router)
app.include_router(admin.router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers ask for /favicon.ico on their own; a PNG is accepted under this name
    return FileResponse(BASE_DIR / "static" / "apple-touch-icon.png", media_type="image/png")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/directions", status_code=303)
