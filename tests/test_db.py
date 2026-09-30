import sqlite3

from pricecharter import db

# games table as shipped in S0, before platform/region existed
S0_GAMES = """
CREATE TABLE games (
    id INTEGER PRIMARY KEY, console TEXT NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
    image_url TEXT, genre TEXT, release_date TEXT, publisher TEXT, developer TEXT, model_number TEXT,
    player_count TEXT, upc TEXT, asin TEXT, epid TEXT, list_rank INTEGER,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')), last_list_at TEXT, last_detail_at TEXT,
    UNIQUE (console, slug)
)"""


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_new_db_has_region_columns(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    assert {"platform", "region"} <= _cols(conn, "games")


def test_migrates_old_db_and_backfills(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(S0_GAMES)
    old.execute("INSERT INTO games (id, console, slug, name) VALUES (1, 'famicom', 'a', 'A'), (2, 'pal-wii', 'b', 'B')")
    old.commit()
    old.close()

    conn = db.connect(path)
    rows = {r["id"]: (r["platform"], r["region"]) for r in conn.execute("SELECT * FROM games")}
    assert rows == {1: ("nes", "ntsc-j"), 2: ("wii", "pal")}


def test_upsert_list_game_sets_region(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    g = {"id": 7, "console": "jp-psp", "slug": "s", "name": "N", "image_url": None,
         "loose_cents": 100, "cib_cents": 200, "new_cents": 300}
    db.upsert_list_game(conn, g, 1, "2026-09-30")
    r = conn.execute("SELECT platform, region FROM games WHERE id = 7").fetchone()
    assert tuple(r) == ("psp", "ntsc-j")


def _game(conn, id, console, rank, detail_at=None):
    db.upsert_list_game(conn, {"id": id, "console": console, "slug": f"g{id}", "name": f"G{id}", "image_url": None},
                        rank, "2026-09-30")
    if detail_at:
        conn.execute("UPDATE games SET last_detail_at = ? WHERE id = ?", (detail_at, id))


def test_games_due_across_consoles_never_fetched_first(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    _game(conn, 1, "nes", 1, "2026-01-01 00:00:00")   # stale
    _game(conn, 2, "nes", 2)                           # never
    _game(conn, 3, "pal-nes", 1)                       # never
    _game(conn, 4, "pal-nes", 2, "2025-01-01 00:00:00")  # older stale
    _game(conn, 5, "famicom", 1)                       # not selected
    due = [r["id"] for r in db.games_due(conn, ["nes", "pal-nes"], stale_days=7, limit=None)]
    assert due == [3, 2, 4, 1]
    assert [r["id"] for r in db.games_due(conn, ["nes", "pal-nes"], 7, limit=2)] == [3, 2]


def test_list_fresh(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    assert not db.list_fresh(conn, "nes", hours=20)
    run = db.start_run(conn, "list", "nes")
    db.finish_run(conn, run, 100, 1, "boom")
    assert not db.list_fresh(conn, "nes", hours=20)       # failed runs don't count
    run = db.start_run(conn, "list", "nes")
    db.finish_run(conn, run, 100, 0)
    assert db.list_fresh(conn, "nes", hours=20)
    assert not db.list_fresh(conn, "pal-nes", hours=20)
    conn.execute("UPDATE crawl_runs SET finished_at = datetime('now', '-21 hours')")
    assert not db.list_fresh(conn, "nes", hours=20)


def test_save_detail_stores_esrb(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    _game(conn, 1, "nes", 1)
    detail = {"details": {"esrb": "Everyone"}, "current": {}, "history": {}, "sales": {}}
    db.save_detail(conn, 1, detail, "2026-09-30")
    assert conn.execute("SELECT esrb FROM games WHERE id = 1").fetchone()[0] == "Everyone"
