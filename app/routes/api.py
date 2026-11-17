from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.deps import DB
from app.i18n import get_ui_lang, translate
from app.services.geocoding import ATTRIBUTION, GeocodingError, NominatimClient, get_geocoder

router = APIRouter(prefix="/api")


@router.get("/geocode")
def geocode(
    request: Request,
    conn: DB,
    geocoder: Annotated[NominatimClient, Depends(get_geocoder)],
    q: Annotated[str, Query(min_length=3, max_length=200)],
):
    try:
        results, cached = geocoder.search(conn, q.strip())
    except GeocodingError as exc:
        return JSONResponse({"error": translate(get_ui_lang(request), exc.msg)}, status_code=502)
    return {
        "results": [r.to_dict() for r in results],
        "cached": cached,
        "attribution": ATTRIBUTION,
    }
