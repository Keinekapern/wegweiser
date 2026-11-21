"""Server-side PDFs: a single printout as PDF, and the bulk export as ZIP."""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app import categories, config, db, export_names, languages
from app.deps import DB, Allowed, templates
from app.i18n import (DIRECTIONS_LANGUAGES, Msg, directions_language_options, get_ui_lang,
                      normalize_directions_lang, translate, translator)
from app.services import export, pdf

router = APIRouter()


def _ints(values) -> list[int]:
    out = []
    for v in values:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return out


def _content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


# --- single PDF of a printout ---

@router.get("/directions/pdf")
def directions_pdf(request: Request, conn: DB, _: Allowed("export.pdf"),
                   location_id: int, destination_id: int, lang: str | None = None):
    dest = db.get_destination(conn, destination_id)
    if dest is None or db.get_location(conn, location_id) is None:
        raise HTTPException(404, translate(get_ui_lang(request), "Standort oder Ziel wurde nicht gefunden."))
    lang = languages.normalize(conn, lang)
    params = request.url.query
    try:
        with pdf.open_renderer(lock_timeout=20) as renderer:
            data, _state, error = renderer.render(f"/directions/print?{params}")
    except pdf.RendererBusy:
        raise HTTPException(503, translate(get_ui_lang(request),
                            "Gerade läuft ein PDF-Export. Bitte in ein paar Minuten erneut versuchen."))
    except pdf.PdfError as exc:
        raise HTTPException(500, str(exc))
    if not data:
        raise HTTPException(502, error or "PDF")
    name = export_names.pdf_name(export_names.safe(dest.name), lang, ui=get_ui_lang(request))
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": _content_disposition(name)})


# --- bulk export ---

def _form_context(request: Request, conn, *, errors=None, form=None):
    locations = db.list_locations(conn)
    destinations = db.list_destinations(conn)
    return {
        "locations": locations,
        "destinations": destinations,
        "assignments": db.destination_location_ids(conn),
        "categories": categories.BY_KEY,
        "languages": languages.options(conn, get_ui_lang(request)),
        "modes": export_names.MODE_LABELS,
        "errors": errors or [],
        "form": form or {"location_ids": [l.id for l in locations][:1], "langs": ["de"],
                         "modes": ["auto"], "orientation": "portrait", "bw": False,
                         "destination_ids": [d.id for d in destinations]},
        "busy": export.busy(),
        "max_files": export.MAX_FILES,
    }


@router.get("/export", response_class=HTMLResponse)
def export_page(request: Request, conn: DB, _: Allowed("export.bulk")):
    return templates.TemplateResponse(request, "export.html", _form_context(request, conn))


@router.post("/export", response_class=HTMLResponse)
async def export_start(request: Request, conn: DB, _: Allowed("export.bulk")):
    data = await request.form()
    form = {
        "location_ids": _ints(data.getlist("location_ids")),
        "destination_ids": _ints(data.getlist("destination_ids")),
        "langs": [l for l in data.getlist("langs") if l in set(languages.enabled(conn))],
        "modes": [m for m in data.getlist("modes") if m in export.MODES],
        "orientation": "landscape" if data.get("orientation") == "landscape" else "portrait",
        "bw": data.get("bw") == "1",
    }
    ui_lang = get_ui_lang(request)
    errors = []
    if not form["location_ids"]:
        errors.append(Msg("Bitte mindestens einen Standort wählen."))
    if not form["destination_ids"]:
        errors.append(Msg("Bitte mindestens ein Ziel wählen."))
    if not form["langs"]:
        errors.append(Msg("Bitte mindestens eine Sprache wählen."))
    if not form["modes"]:
        errors.append(Msg("Bitte mindestens ein Verkehrsmittel wählen."))
    req = export.ExportRequest(**form, ui_lang=ui_lang)
    if not errors:
        items, _name = export.plan(conn, req)
        if not items:
            errors.append(Msg("Für diese Auswahl gibt es keine Ziele: Die gewählten Ziele werden bei den gewählten Standorten nicht angeboten."))
        elif len(items) > export.MAX_FILES:
            errors.append(Msg("Das wären {n} PDFs, höchstens {max} sind auf einmal möglich. Bitte weniger Ziele oder Sprachen wählen.",
                              n=len(items), max=export.MAX_FILES))
    if not errors and export.busy():
        errors.append(Msg("Gerade läuft schon ein Export. Bitte warten, bis er fertig ist."))
    if errors:
        return templates.TemplateResponse(request, "export.html",
                                          _form_context(request, conn, errors=errors, form=form),
                                          status_code=422)
    job = export.start(conn, req, lambda j: overview_html(j, ui_lang))
    return RedirectResponse(f"/export/{job.id}", status_code=303)


def _job(job_id: str) -> export.Job:
    job = export.get(job_id)
    if job is None:
        raise HTTPException(404)
    return job


@router.get("/export/{job_id}", response_class=HTMLResponse)
def export_status(request: Request, job_id: str, _: Allowed("export.bulk")):
    job = _job(job_id)
    return templates.TemplateResponse(request, "export_status.html",
                                      {"job": job, "state": job.as_dict()})


@router.get("/export/{job_id}/status")
def export_status_json(job_id: str, _: Allowed("export.bulk")):
    return _job(job_id).as_dict()


@router.get("/export/{job_id}/download")
def export_download(job_id: str, _: Allowed("export.bulk")):
    job = _job(job_id)
    if job.status != "done" or not job.zip_path.exists():
        raise HTTPException(404)
    return FileResponse(job.zip_path, media_type="application/zip",
                        headers={"Content-Disposition": _content_disposition(job.zip_name)})


def overview_html(job: export.Job, ui_lang: str) -> str:
    """Übersicht.pdf: what the ZIP contains, and what could not be created."""
    req = job.request
    problem_paths = {p for p, reason in job.problems if reason != export.INCOMPLETE_MAP}
    rows = {}
    for it in job.items:
        key = (it.location.name, it.destination.name)
        row = rows.setdefault(key, {"location": it.location.name, "destination": it.destination.name,
                                    "folder": it.path.rsplit("/", 1)[0], "count": 0})
        if it.path not in problem_paths:
            row["count"] += 1
    template = templates.env.get_template("export_overview.html")
    return template.render(
        t=translator(ui_lang), ui_lang=ui_lang, job=job, rows=list(rows.values()), today=date.today(),
        languages=sorted(export_names.language_name(l, ui_lang) for l in req.langs),
        modes=[export_names.mode_label(m, ui_lang) for m in req.modes],
        several_locations=len({it.location.id for it in job.items}) > 1,
        transit_source=config.transit_attribution(), route_source=config.route_attribution(),
        created_count=len(job.items) - len(problem_paths))
