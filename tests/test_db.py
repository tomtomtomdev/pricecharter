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
