"""FastAPI app: server-rendered pages over a read-only SQLite connection."""

import math
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import queries

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["usd"] = lambda c: "" if c is None else f"${c / 100:,.2f}"
templates.env.filters["pct"] = lambda x: (
    "" if x is None or x != x else "0%" if round(x * 100) == 0 else f"{x:+.0%}".replace("-", "−"))
# series_metrics stores log returns; show them as simple % changes
templates.env.filters["logpct"] = lambda x: "" if x is None or x != x else templates.env.filters["pct"](math.exp(x) - 1)
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

    @app.get("/games/{game_id}")
    def game_page(request: Request, conn: Conn, game_id: int):
        g = queries.game(conn, game_id)
        if g is None:
            raise HTTPException(404, f"no game {game_id}")
        hist = queries.history(conn, game_id)
        return templates.TemplateResponse(request, "game.html", {
            "g": g, "sales": queries.sales(conn, game_id),
            # a list, not a dict: tojson sorts keys and the series order is loose, cib, new
            "chart": [{"cond": c, "x": [m for m, _ in p], "y": [round(v / 100, 2) for _, v in p]}
                      for c, p in hist.items()],
            "table": _history_table(hist), "analysis": queries.game_analysis(conn, game_id),
        })

    @app.get("/consoles/{console}")
    def console_page(request: Request, conn: Conn, console: str, cond: Literal["loose", "cib", "new"] = "loose"):
        cov = next((r for r in queries.coverage(conn, stale_days) if r["console"] == console), None)
        if cov is None:
            raise HTTPException(404, f"no titles crawled for console {console}")
        return templates.TemplateResponse(request, "console.html", {
            "console": console, "cov": cov, "cond": cond, "stale_days": stale_days,
            "index": queries.console_index_series(conn, console),
            "has_analysis": queries.table_exists(conn, "series_metrics"),
            "risers": queries.movers(conn, console, cond),
            "fallers": queries.movers(conn, console, cond, rising=False),
        })

    @app.get("/insights")
    def insights(request: Request, conn: Conn, cond: Literal["loose", "cib", "new"] = "loose"):
        res = _stored(app, conn)
        if res is None:
            return templates.TemplateResponse(request, "insights.html", {"ctx": None, "cond": cond})
        from ..analysis import report

        ctx = report.context(res)
        patterns = [{**r, "links": _example_links(r["example_ids"], res.games)} for r in ctx["patterns"].get(cond, [])]
        return templates.TemplateResponse(request, "insights.html", {
            "ctx": ctx, "cond": cond, "p": ctx["p"], "patterns": patterns,
            "factors": ctx["factors"].get(cond, []), "signals": ctx["signals"].get(cond, []),
            "factor_bars": report.factor_bars(res.factor_lift).get(cond),
            "cluster_lines": report.cluster_traces(res.cluster_summary) if not res.cluster_summary.empty else [],
        })

    @app.get("/watchlist")
    def watchlist(
        request: Request, conn: Conn, cond: Literal["loose", "cib", "new"] = "loose", console: str = "",
        sort: Literal["score", "price", "name", "model"] = "score",
    ):
        rows = queries.watchlist(conn, cond=cond, console=console or None, sort=sort)
        return templates.TemplateResponse(request, "watchlist.html", {
            "rows": rows, "cond": cond, "console": console, "sort": sort,
            "consoles": queries.watchlist_consoles(conn),
            "has_model": bool(rows) and any(r["model_pred"] is not None for r in rows),
        })

    @app.get("/compare")
    def compare(
        request: Request, conn: Conn, ids: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI copies it)
        cond: Literal["loose", "cib", "new"] = "loose", mode: Literal["raw", "rebased", "index"] = "raw",
    ):
        picked = _parse_ids(ids)
        series = queries.compare_series(conn, picked, cond=cond, mode=mode)
        for sr in series:  # color follows the title (its chip), even when another title has no data
            sr["slot"] = picked.index(sr["id"]) + 1
        names = {r["id"]: dict(r) for r in conn.execute(
            f"SELECT id, name, console FROM games WHERE id IN ({','.join('?' * len(picked))})", picked)}
        chips = [{**names[i], "without": ",".join(str(j) for j in picked if j != i)} for i in picked if i in names]
        return templates.TemplateResponse(request, "compare.html", {
            "series": series, "chips": chips, "ids": ",".join(map(str, picked)), "cond": cond, "mode": mode,
            "has_index": queries.table_exists(conn, "console_index"), "full": len(picked) >= queries.MAX_COMPARE,
            "missing": [c for c in chips if c["id"] not in {s["id"] for s in series}],
        })

    @app.get("/compare/suggest")
    def compare_suggest(request: Request, conn: Conn, q: str = "", ids: str = "", cond: str = "loose",
                        mode: str = "raw"):
        picked = _parse_ids([ids])
        rows, _ = queries.search_games(conn, q=q, sort="rank", per_page=8) if q.strip() else ([], 0)
        return templates.TemplateResponse(request, "_compare_suggest.html", {
            "rows": [r for r in rows if r["id"] not in picked],
            "href": lambda gid: "/compare?" + urlencode({"ids": ",".join(map(str, [*picked, gid])),
                                                         "cond": cond, "mode": mode}),
        })

    @app.get("/report", response_class=HTMLResponse)
    def full_report(conn: Conn):
        res = _stored(app, conn)
        if res is None:
            raise HTTPException(404, "no analysis yet; run ./run.sh analyze")
        from ..analysis import report

        return report.render_html(res)

    return app


def _parse_ids(raw: list[str]) -> list[int]:
    """`ids=1,2&ids=3` → [1, 2, 3], de-duplicated, capped at MAX_COMPARE."""
    out: list[int] = []
    for part in ",".join(raw).split(","):
        if not part.strip():
            continue
        try:
            gid = int(part)
        except ValueError:
            raise HTTPException(422, f"bad title id {part!r}") from None
        if gid not in out:
            out.append(gid)
    return out[: queries.MAX_COMPARE]


_stored_lock = threading.Lock()


def _stored(app: FastAPI, conn: sqlite3.Connection):
    """Latest persisted AnalysisResult, reloaded only when a new analysis run appears."""
    last = queries.last_analysis(conn)
    if last is None:
        return None
    key = (last["id"], last["ran_at"])
    with _stored_lock:
        if getattr(app.state, "stored_key", None) != key:
            from ..analysis.stored import load_stored  # pandas stack only when analysis pages are used

            app.state.stored, app.state.stored_key = load_stored(conn), key
        return app.state.stored


def _example_links(ids: str | None, games) -> list[dict]:
    out = []
    for gid in filter(None, (ids or "").split(",")):
        if int(gid) in games.index:
            g = games.loc[int(gid)]
            out.append({"id": int(gid), "name": g["name"], "console": g["console"]})
    return out


def _history_table(hist: dict[str, list[tuple[str, int]]]) -> list[dict]:
    """Newest-first month rows with one column per condition (the chart's table view)."""
    rows: dict[str, dict] = {}
    for cond, pts in hist.items():
        for month, cents in pts:
            rows.setdefault(month, {"month": month})[cond] = cents
    return [rows[m] for m in sorted(rows, reverse=True)]
