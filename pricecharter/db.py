import sqlite3
from pathlib import Path

from .consoles import all_consoles, by_slug

SCHEMA = Path(__file__).with_name("schema.sql")

# Columns added after the first release; connect() adds any that an older DB lacks.
ADDED_COLUMNS = {
    "games": {"platform": "TEXT", "region": "TEXT"},
}


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    for table, cols in ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.executemany(
        "UPDATE games SET platform = ?, region = ? WHERE console = ? AND (platform IS NULL OR region IS NULL)",
        [(c.platform, c.region, c.slug) for c in all_consoles()],
    )
    conn.execute("CREATE INDEX IF NOT EXISTS games_region ON games (platform, region)")
    conn.commit()


def upsert_list_game(conn: sqlite3.Connection, g: dict, rank: int, day: str) -> None:
    conn.execute(
        """
        INSERT INTO games (id, console, platform, region, slug, name, image_url, list_rank, last_list_at)
        VALUES (:id, :console, :platform, :region, :slug, :name, :image_url, :rank, datetime('now'))
        ON CONFLICT (id) DO UPDATE SET
            console = excluded.console, platform = excluded.platform, region = excluded.region,
            slug = excluded.slug, name = excluded.name,
            image_url = excluded.image_url, list_rank = excluded.list_rank,
            last_list_at = excluded.last_list_at
        """,
        {**g, "rank": rank, "platform": c.platform if (c := by_slug(g["console"])) else None,
         "region": c.region if c else None},
    )
    save_snapshot(conn, g["id"], day, "list", g)


def save_snapshot(conn: sqlite3.Connection, game_id: int, day: str, source: str, prices: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO price_snapshots (game_id, captured_on, source, loose_cents, cib_cents, new_cents)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (game_id, day, source, prices.get("loose_cents"), prices.get("cib_cents"), prices.get("new_cents")),
    )


def save_detail(conn: sqlite3.Connection, game_id: int, detail: dict, day: str) -> None:
    d = detail["details"]
    conn.execute(
        """
        UPDATE games SET genre = :genre, release_date = :release_date, publisher = :publisher,
            developer = :developer, model_number = :model_number, player_count = :player_count,
            upc = :upc, asin = :asin, epid = :epid, last_detail_at = datetime('now')
        WHERE id = :id
        """,
        {k: d.get(k) for k in (
            "genre", "release_date", "publisher", "developer", "model_number",
            "player_count", "upc", "asin", "epid",
        )} | {"id": game_id},
    )
    save_snapshot(conn, game_id, day, "detail", detail["current"])
    conn.executemany(
        """
        INSERT INTO price_history (game_id, condition, month, price_cents) VALUES (?, ?, ?, ?)
        ON CONFLICT (game_id, condition, month) DO UPDATE SET price_cents = excluded.price_cents
        """,
        [(game_id, cond, m, c) for cond, pts in detail["history"].items() for m, c in pts],
    )
    conn.executemany(
        """
        INSERT INTO sales (game_id, condition, sale_id, sale_date, title, price_cents, source, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (game_id, condition, sale_id) DO UPDATE SET
            sale_date = excluded.sale_date, title = excluded.title,
            price_cents = excluded.price_cents, source = excluded.source, url = excluded.url
        """,
        [
            (game_id, cond, s["sale_id"], s["sale_date"], s["title"], s["price_cents"], s["source"], s["url"])
            for cond, rows in detail["sales"].items()
            for s in rows
        ],
    )


def games_due(conn: sqlite3.Connection, console: str, stale_days: float, limit: int | None) -> list[sqlite3.Row]:
    sql = """
        SELECT id, console, slug, name FROM games
        WHERE console = ?
          AND (last_detail_at IS NULL OR last_detail_at < datetime('now', ?))
        ORDER BY last_detail_at IS NOT NULL, list_rank
    """
    params: list = [console, f"-{stale_days} days"]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def start_run(conn: sqlite3.Connection, stage: str, console: str) -> int:
    cur = conn.execute("INSERT INTO crawl_runs (stage, console) VALUES (?, ?)", (stage, console))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, ok: int, failed: int, error: str | None = None) -> None:
    conn.execute(
        "UPDATE crawl_runs SET finished_at = datetime('now'), ok = ?, failed = ?, error = ? WHERE id = ?",
        (ok, failed, error, run_id),
    )
    conn.commit()
