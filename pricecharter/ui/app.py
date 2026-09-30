"""FastAPI app: server-rendered pages over a read-only SQLite connection."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import queries

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["usd"] = lambda c: "" if c is None else f"${c / 100:,.2f}"
templates.env.filters["pct"] = lambda x: "" if x is None else f"{x:+.0%}"
PER_PAGE = 50


def readonly_connect(path: Path) -> sqlite3.Connection:
    # mode=ro: browsing never takes a write lock, so it's safe while the crawl runs (WAL).
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = readonly_connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def create_app(db_path: Path, stale_days: float = 7) -> FastAPI:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found; run the crawl first")
    app = FastAPI(title="pricecharter", docs_url=None, redoc_url=None)
    app.state.db_path = db_path
    app.state.stale_days = stale_days
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.get("/healthz")
    def healthz(conn: Conn) -> dict:
        return {"ok": True, "games": conn.execute("SELECT count(*) FROM games").fetchone()[0]}

    @app.get("/")
    def dashboard(request: Request, conn: Conn):
        cov = queries.coverage(conn, stale_days)
        totals = {k: sum(r[k] or 0 for r in cov) for k in ("listed", "fetched", "stale", "never", "with_history")}
        return templates.TemplateResponse(request, "dashboard.html", {
            "coverage": cov, "totals": totals, "stale_days": stale_days,
            "runs": queries.recent_runs(conn), "analysis": queries.last_analysis(conn),
        })

    @app.get("/games")
    def games(
        request: Request, conn: Conn, q: str = "", console: str = "", platform: str = "", region: str = "",
        genre: str = "", sort: Literal["price", "rank", "name", "excess"] = "price",
        cond: Literal["loose", "cib", "new"] = "loose", page: Annotated[int, Query(ge=1)] = 1,
    ):
        filters = {"console": console, "platform": platform, "region": region, "genre": genre}
        rows, total = queries.search_games(conn, q=q, sort=sort, cond=cond, page=page, per_page=PER_PAGE, **filters)
        ctx = {
            "rows": rows, "total": total, "page": page, "pages": max(1, -(-total // PER_PAGE)),
            "q": q, "sort": sort, "cond": cond, "filters": filters,
            "has_analysis": queries.table_exists(conn, "series_metrics"),
            "query": lambda **kw: urlencode({k: v for k, v in (
                {"q": q, **filters, "sort": sort, "cond": cond, "page": page} | kw).items() if v}),
        }
        if request.headers.get("HX-Request"):
            return templates.TemplateResponse(request, "_games_results.html", ctx)
        return templates.TemplateResponse(request, "games.html", ctx | {"facets": queries.facets(conn)})

    return app
