from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.services.common import MAX_QUERY_LENGTH, SearchError, SearchNotConfigured
from app.services.google_parser import GoogleBlockedError
from app.services.search import (
    SerpApiSearchService,
    response_dict,
    results_to_csv,
    validate_query,
)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(search_service=None) -> FastAPI:
    app = FastAPI(title="Google Organic Results", docs_url=None, redoc_url=None)
    # SerpApi is the single active provider. Direct Google remains an
    # experimental implementation and is never used as a fallback.
    app.state.search_service = search_service or SerpApiSearchService()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/search")
    async def search(
        request: Request,
        q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
        format: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
    ) -> Response:
        try:
            query = validate_query(q)
            result = await request.app.state.search_service.search(query)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
        except SearchNotConfigured as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})
        except GoogleBlockedError as exc:
            return JSONResponse(status_code=502, content={"detail": str(exc)})
        except SearchError as exc:
            return JSONResponse(status_code=502, content={"detail": str(exc)})

        if format == "csv":
            filename = "google-organic-results.csv"
            return Response(
                content="\ufeff" + results_to_csv(result),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        return JSONResponse(content=response_dict(result))

    return app


app = create_app()
