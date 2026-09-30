"""Read-only SQL for the web UI. Analysis tables are optional: they exist only after `analyze`."""

import math
import sqlite3

from ..consoles import all_consoles

_ORDER = {c.slug: i for i, c in enumerate(all_consoles())}


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def coverage(conn: sqlite3.Connection, stale_days: float) -> list[dict]:
    rows = conn.execute(
        """
        SELECT g.console, g.platform, g.region,
               count(*) AS listed,
               count(g.last_detail_at) AS fetched,
               sum(g.last_detail_at < datetime('now', ?)) AS stale,
               sum(g.last_detail_at IS NULL) AS never,
               count(h.game_id) AS with_history,
               max(g.last_list_at) AS last_list_at,
               max(g.last_detail_at) AS last_detail_at
        FROM games g
        LEFT JOIN (SELECT DISTINCT game_id FROM price_history) h ON h.game_id = g.id
        GROUP BY g.console
        """,
        (f"-{stale_days} days",),
    ).fetchall()
    return sorted((dict(r) for r in rows), key=lambda r: (_ORDER.get(r["console"], len(_ORDER)), r["console"]))


def recent_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT ?", (limit,))]


def last_analysis(conn: sqlite3.Connection) -> dict | None:
    if not table_exists(conn, "analysis_runs"):
        return None
    row = conn.execute("SELECT * FROM analysis_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


CONDITIONS = ("loose", "cib", "new")
SORTS = ("price", "rank", "name", "excess")
FILTERS = ("console", "platform", "region", "genre")


def current_price_sql(cond: str, alias: str = "g") -> str:
    """Latest crawled price for one condition: newest snapshot, else the last monthly history point."""
    assert cond in CONDITIONS
    return f"""COALESCE(
        (SELECT s.{cond}_cents FROM price_snapshots s WHERE s.game_id = {alias}.id AND s.{cond}_cents IS NOT NULL
         ORDER BY s.captured_on DESC, s.source = 'detail' DESC LIMIT 1),
        (SELECT h.price_cents FROM price_history h WHERE h.game_id = {alias}.id AND h.condition = '{cond}'
         ORDER BY h.month DESC LIMIT 1))"""


def facets(conn: sqlite3.Connection) -> dict[str, list[str]]:
    out = {}
    for col in FILTERS:
        vals = [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM games WHERE {col} IS NOT NULL")]
        out[col] = sorted(vals, key=lambda v: (_ORDER.get(v, len(_ORDER)), v)) if col == "console" else sorted(vals)
    return out


def search_games(
    conn: sqlite3.Connection, q: str | None = None, sort: str = "price", cond: str = "loose",
    page: int = 1, per_page: int = 50, **filters: str | None,
) -> tuple[list[dict], int]:
    assert sort in SORTS and cond in CONDITIONS
    where, params = [], []
    if q:
        where.append("g.name LIKE ? ESCAPE '\\'")
        params.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    for col in FILTERS:
        if filters.get(col):
            where.append(f"g.{col} = ?")
            params.append(filters[col])
    unknown = set(filters) - set(FILTERS)
    assert not unknown, unknown
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT count(*) FROM games g {where_sql}", params).fetchone()[0]

    has_metrics = table_exists(conn, "series_metrics")
    join = "LEFT JOIN series_metrics sm ON sm.game_id = g.id AND sm.condition = ?" if has_metrics else ""
    if sort == "excess" and not has_metrics:
        sort = "price"
    order = {
        "price": f"{current_price_sql(cond)} DESC NULLS LAST",
        "rank": "g.list_rank IS NULL, g.list_rank",
        "name": "g.name COLLATE NOCASE",
        "excess": "sm.excess_36m DESC NULLS LAST",
    }[sort]
    ids = [r[0] for r in conn.execute(
        f"SELECT g.id FROM games g {join} {where_sql} ORDER BY {order}, g.id LIMIT ? OFFSET ?",
        ([cond] if has_metrics else []) + params + [per_page, (max(page, 1) - 1) * per_page],
    )]
    if not ids:
        return [], total
    excess = "sm.excess_36m" if has_metrics else "NULL"
    rows = conn.execute(
        f"""SELECT g.*, {current_price_sql('loose')} AS loose_cents, {current_price_sql('cib')} AS cib_cents,
                   {current_price_sql('new')} AS new_cents, {excess} AS excess_36m
            FROM games g {join} WHERE g.id IN ({','.join('?' * len(ids))})""",
        ([cond] if has_metrics else []) + ids,
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids], total


def game(conn: sqlite3.Connection, game_id: int) -> dict | None:
    row = conn.execute(
        f"""SELECT g.*, {current_price_sql('loose')} AS loose_cents, {current_price_sql('cib')} AS cib_cents,
                   {current_price_sql('new')} AS new_cents
            FROM games g WHERE g.id = ?""",
        (game_id,),
    ).fetchone()
    return dict(row) if row else None


def history(conn: sqlite3.Connection, game_id: int) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    for r in conn.execute(
        "SELECT condition, month, price_cents FROM price_history WHERE game_id = ? ORDER BY condition, month",
        (game_id,),
    ):
        out.setdefault(r["condition"], []).append((r["month"], r["price_cents"]))
    return {c: out[c] for c in CONDITIONS if c in out}


def sales(conn: sqlite3.Connection, game_id: int, limit: int = 60) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM sales WHERE game_id = ? ORDER BY sale_date DESC, condition LIMIT ?", (game_id, limit),
    )]


def game_analysis(conn: sqlite3.Connection, game_id: int) -> dict | None:
    """Latest analysis for one title, or None if `analyze` hasn't run. Optional tables degrade to empty."""
    if not table_exists(conn, "series_metrics"):
        return None
    shape = ("(SELECT cc.shape FROM curve_clusters cc WHERE cc.game_id = sm.game_id AND cc.condition = sm.condition)"
             if table_exists(conn, "curve_clusters") else "NULL")
    metrics = [dict(r) for r in conn.execute(
        f"""SELECT sm.*, {shape} AS shape FROM series_metrics sm WHERE sm.game_id = ?
            ORDER BY CASE sm.condition WHEN 'loose' THEN 0 WHEN 'cib' THEN 1 ELSE 2 END""",
        (game_id,),
    )]
    watch = [dict(r) for r in conn.execute("SELECT * FROM watchlist WHERE game_id = ? ORDER BY score DESC",
                                           (game_id,))] if table_exists(conn, "watchlist") else []
    for w in watch:
        w["patterns"] = [p.strip() for p in (w.get("matched") or "").split(" | ") if p.strip()]
    return {"metrics": metrics, "watchlist": watch, "index": _rebased_index(conn, game_id)}


def _rebased_index(conn: sqlite3.Connection, game_id: int) -> list[dict]:
    """Console index per condition scaled to start at the title's first price, over the title's months."""
    if not table_exists(conn, "console_index"):
        return []
    console = conn.execute("SELECT console FROM games WHERE id = ?", (game_id,)).fetchone()[0]
    out = []
    for cond, pts in history(conn, game_id).items():
        first_month, first_cents = pts[0]
        rows = conn.execute(
            """SELECT month, level FROM console_index WHERE console = ? AND condition = ? AND month BETWEEN ? AND ?
               AND level IS NOT NULL ORDER BY month""",
            (console, cond, first_month, pts[-1][0]),
        ).fetchall()
        if not rows or rows[0]["month"] != first_month:
            continue
        base = rows[0]["level"]
        out.append({"cond": cond, "x": [r["month"] for r in rows],
                    "y": [round(first_cents / 100 * math.exp(r["level"] - base), 2) for r in rows]})
    return out


def console_index_series(conn: sqlite3.Connection, console: str) -> list[dict]:
    """Median-title index per condition as % change since the index starts."""
    if not table_exists(conn, "console_index"):
        return []
    out = []
    for cond in CONDITIONS:
        rows = conn.execute(
            "SELECT month, level FROM console_index WHERE console = ? AND condition = ? AND level IS NOT NULL"
            " ORDER BY month", (console, cond),
        ).fetchall()
        if rows:
            out.append({"cond": cond, "x": [r["month"] for r in rows],
                        "y": [round((math.exp(r["level"]) - 1) * 100, 1) for r in rows]})
    return out


def movers(conn: sqlite3.Connection, console: str, cond: str, n: int = 15, rising: bool = True) -> list[dict]:
    """Titles with the largest (or smallest) 3-year excess return vs their console index."""
    if not table_exists(conn, "series_metrics"):
        return []
    assert cond in CONDITIONS
    return [dict(r) for r in conn.execute(
        f"""SELECT g.id, g.name, g.console, g.genre, sm.excess_36m, sm.ret_36m, sm.rising,
                   {current_price_sql(cond)} AS price_cents
            FROM series_metrics sm JOIN games g ON g.id = sm.game_id
            WHERE sm.console = ? AND sm.condition = ? AND sm.excess_36m IS NOT NULL
            ORDER BY sm.excess_36m {'DESC' if rising else 'ASC'} LIMIT ?""",
        (console, cond, n),
    )]


WATCH_SORTS = {"score": "w.score DESC", "price": "w.price_cents DESC", "name": "w.name COLLATE NOCASE",
               "model": "w.model_pred DESC NULLS LAST"}


def watchlist(
    conn: sqlite3.Connection, cond: str = "loose", console: str | None = None, sort: str = "score",
) -> list[dict] | None:
    """Titles matching rising patterns, from the latest analysis; None if it hasn't run."""
    if not table_exists(conn, "watchlist"):
        return None
    params: list = [cond]
    where = "w.condition = ?"
    if console:
        where += " AND w.console = ?"
        params.append(console)
    rows = [dict(r) for r in conn.execute(
        f"SELECT w.* FROM watchlist w WHERE {where} ORDER BY {WATCH_SORTS[sort]}, w.game_id", params)]
    for r in rows:
        r["patterns"] = [p.strip() for p in (r.get("matched") or "").split(" | ") if p.strip()]
    return rows


def watchlist_consoles(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "watchlist"):
        return []
    vals = [r[0] for r in conn.execute("SELECT DISTINCT console FROM watchlist")]
    return sorted(vals, key=lambda v: (_ORDER.get(v, len(_ORDER)), v))


MAX_COMPARE = 6


def compare_series(conn: sqlite3.Connection, ids: list[int], cond: str = "loose", mode: str = "raw") -> list[dict]:
    """One line per title. raw = $; rebased = 100 at the common start month; index = rebased and divided by
    the title's own console index (so 100 → 150 means 50% better than the median title on that console)."""
    assert cond in CONDITIONS and mode in ("raw", "rebased", "index")
    if mode == "index" and not table_exists(conn, "console_index"):
        return []
    out = []
    for gid in ids:
        g = conn.execute("SELECT id, name, console FROM games WHERE id = ?", (gid,)).fetchone()
        pts = history(conn, gid).get(cond) if g else None
        if not pts:
            continue
        if mode == "index":
            level = dict(conn.execute(
                "SELECT month, level FROM console_index WHERE console = ? AND condition = ? AND level IS NOT NULL",
                (g["console"], cond)).fetchall())
            pts = [(m, c, level[m]) for m, c in pts if m in level]
        else:
            pts = [(m, c, 0.0) for m, c in pts]
        if pts:
            out.append({"id": g["id"], "name": g["name"], "console": g["console"], "pts": pts})
    if mode != "raw" and out:
        start = max(s["pts"][0][0] for s in out)
        out = [s for s in out if s["pts"][-1][0] >= start]
    for s in out:
        pts = s.pop("pts")
        if mode == "raw":
            s["x"], s["y"] = [m for m, _, _ in pts], [c / 100 for _, c, _ in pts]
            continue
        pts = [p for p in pts if p[0] >= start]
        _, c0, l0 = pts[0]
        s["x"] = [m for m, _, _ in pts]
        s["y"] = [round(100 * c / c0 * math.exp(l0 - lv), 3) for _, c, lv in pts]
    return out
