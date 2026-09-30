"""FastAPI app: server-rendered pages over a read-only SQLite connection."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")


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


def create_app(db_path: Path) -> FastAPI:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found; run the crawl first")
    app = FastAPI(title="pricecharter", docs_url=None, redoc_url=None)
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.get("/healthz")
    def healthz(conn: Conn) -> dict:
        return {"ok": True, "games": conn.execute("SELECT count(*) FROM games").fetchone()[0]}

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {})

    return app
