"""Read-only SQL for the web UI. Analysis tables are optional: they exist only after `analyze`."""

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
