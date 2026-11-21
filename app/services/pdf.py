"""Server-side PDFs of the print view, rendered by headless Chromium (Playwright).

The browser loads the app's own print view over HTTP (PDF_BASE_URL, inside the container
http://127.0.0.1:8000), waits until print.js reports the maps as loaded
(<html data-print-ready="ok|errors">) and prints it with the page's own @page size.

Map tiles: the browser's tile requests are answered from a disk cache (data/tile-cache,
kept 7 days as the OSM tile usage policy asks); missing tiles are fetched one at a time
with the app's User-Agent. All languages of a destination share the same maps, so a bulk
export fetches each tile only once. Only one browser runs at a time (RAM).
"""

import hashlib
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app import config

log = logging.getLogger(__name__)

READY_TIMEOUT_MS = 30_000
TILE_CACHE_DAYS = 7
TILE_MIN_INTERVAL_S = 0.05

# Server PDFs use the bundled Noto Sans first (servers have no reliable system font;
# Chromium would otherwise pick any installed font, e.g. a CJK one, for Latin text)
PDF_FONT_CSS = ('\nbody { font-family: "Noto Sans Arabic", "Noto Sans Tamil", "Noto Sans Ethiopic", '
                '"Noto Sans", sans-serif; }\n')
_PRINT_CSS = re.compile(r"/static/print\.css(\?.*)?$")

# One Chromium at a time for single PDFs and bulk exports alike
render_lock = threading.Lock()


class PdfError(Exception):
    pass


class RendererBusy(PdfError):
    """Another PDF job (e.g. a bulk export) holds the browser."""


def tile_pattern(template: str) -> re.Pattern:
    """Regex for the tile URLs of a Leaflet URL template ({s}, {z}, {x}, {y}, {r})."""
    parts = re.split(r"(\{[a-z]+\})", template)
    regex = "".join({"{s}": "[a-z0-9]+", "{r}": "(@2x)?"}.get(p, r"\d+") if p.startswith("{")
                    else re.escape(p) for p in parts)
    return re.compile(regex + r"(\?.*)?$")


class TileCache:
    def __init__(self, directory: Path, user_agent: str, transport: httpx.BaseTransport | None = None,
                 max_age_days: int = TILE_CACHE_DAYS):
        self.directory = directory
        self.max_age_s = max_age_days * 86400
        self._http = httpx.Client(transport=transport, timeout=20,
                                  headers={"User-Agent": user_agent})
        self._lock = threading.Lock()
        self._last = 0.0
        self.fetched = 0
        self.hits = 0

    def _path(self, url: str) -> Path:
        return self.directory / (hashlib.sha256(url.encode()).hexdigest()[:40] + ".tile")

    def get(self, url: str) -> tuple[bytes, str] | None:
        """(body, content type) from the cache, fetched once if missing; None on failure."""
        path = self._path(url)
        if path.exists() and time.time() - path.stat().st_mtime < self.max_age_s:
            self.hits += 1
            data = path.read_bytes()
            return data, ("image/jpeg" if data[:2] == b"\xff\xd8" else "image/png")
        with self._lock:                      # one request at a time, small gap
            wait = TILE_MIN_INTERVAL_S - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self._http.get(url, headers={"Referer": config.pdf_base_url() + "/"})
            except httpx.HTTPError as exc:
                log.warning("Tile request failed: %s", exc)
                return None
            finally:
                self._last = time.monotonic()
        if resp.status_code != 200:
            log.warning("Tile %s: HTTP %s", url, resp.status_code)
            return None
        self.fetched += 1
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(resp.content)
        tmp.replace(path)
        return resp.content, resp.headers.get("content-type", "image/png")


class Renderer:
    """Context manager around one Chromium; render() many pages with it."""

    def __init__(self, base_url: str | None = None, tiles: TileCache | None = None,
                 lock_timeout: float | None = None):
        self.lock_timeout = lock_timeout      # None = wait as long as needed
        self.base_url = (base_url or config.pdf_base_url()).rstrip("/")
        self.tiles = tiles or TileCache(config.database_path().parent / "tile-cache",
                                        config.user_agent())
        self._tile_re = tile_pattern(config.tile_url())

    def __enter__(self):
        from playwright.sync_api import sync_playwright   # heavy import, only when used
        if not render_lock.acquire(timeout=-1 if self.lock_timeout is None else self.lock_timeout):
            raise RendererBusy("busy")
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(args=["--disable-dev-shm-usage"])
        except Exception as exc:
            render_lock.release()
            raise PdfError(f"Chromium could not be started: {exc}") from exc
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
            self._pw.stop()
        finally:
            render_lock.release()

    def _serve_tile(self, route):
        tile = self.tiles.get(route.request.url)
        if tile is None:
            route.abort()
        else:
            route.fulfill(status=200, body=tile[0], content_type=tile[1],
                          headers={"Cache-Control": "max-age=604800"})

    @staticmethod
    def _print_css(route):
        resp = route.fetch()
        route.fulfill(response=resp, body=resp.text() + PDF_FONT_CSS)

    def render(self, path_and_query: str) -> tuple[bytes, str, str | None]:
        """PDF of a page of the app -> (pdf, "ok"|"errors", error text shown on the page)."""
        page = self._browser.new_page()
        try:
            page.route(self._tile_re, self._serve_tile)
            page.route(_PRINT_CSS, self._print_css)
            resp = page.goto(self.base_url + path_and_query, wait_until="load")
            if resp is None or resp.status != 200:
                return b"", "errors", f"HTTP {resp.status if resp else '?'}"
            error = page.locator(".toolbar .error")
            error_text = error.first.inner_text() if error.count() else None
            page.wait_for_function("document.documentElement.dataset.printReady",
                                   timeout=READY_TIMEOUT_MS)
            state = page.evaluate("document.documentElement.dataset.printReady")
            page.evaluate("document.fonts.ready.then(() => true)")
            pdf = page.pdf(prefer_css_page_size=True, print_background=True)
            return pdf, state, error_text
        finally:
            page.close()

    def render_html(self, html: str) -> bytes:
        """PDF of a standalone HTML document (links relative to the app)."""
        page = self._browser.new_page()
        try:
            page.goto(self.base_url + "/healthz")    # same origin for /static links
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")   # web fonts, not fallbacks
            return page.pdf(format="A4", print_background=True,
                            margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"})
        finally:
            page.close()


def open_renderer(lock_timeout: float | None = None) -> Renderer:
    """Factory (replaced in tests)."""
    return Renderer(lock_timeout=lock_timeout)
